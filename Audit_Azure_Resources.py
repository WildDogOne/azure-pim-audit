import asyncio
import re

from kestra import Kestra

from creds import (
    confluence_page_id,
    confluence_audit_azure_resources_page_name,
    azure_subscription_exclusions,
    azure_subscription_id_exclusions,
    azure_scope_exclusions,
)
from functions.cli import (
    build_parser,
    build_graph_client,
    build_confluence,
    build_azure_credential,
    timer,
)
from functions.confluence import confluence_update_page
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
from functions.functions import get_azure_subscriptions, BENUTZER, ROLLE, SCOPE

logger = Kestra.logger()


def query_resource_graph(query=None, credential=None, subscriptions=None):
    if not query:
        raise ValueError("query_resource_graph requires a non-empty query")

    resource_graph_client = ResourceGraphClient(credential)
    request_options = QueryRequestOptions(result_format="objectArray")
    if not subscriptions:
        query_request = QueryRequest(query=query, options=request_options)
    else:
        query_request = QueryRequest(
            subscriptions=subscriptions, query=query, options=request_options
        )

    response = resource_graph_client.resources(query_request)
    return response.data


def subscription_translate(scope=None, subscription_dict=None):
    regexp = r"(^\/subscriptions\/)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(.*)"
    match = re.search(regexp, scope)
    if match:
        start = match.group(1)
        subscription_id = match.group(2)
        end = match.group(3)
    else:
        return scope

    if subscription_id in subscription_dict:
        subscription = subscription_dict[subscription_id]
        logger.debug(f"Subscription found in Azure: {subscription}")
    else:
        logger.error("Subscription not found in Azure")
        subscription = subscription_id
    for exclusion in azure_subscription_id_exclusions:
        if exclusion == subscription_id:
            return False
    for exclusion in azure_subscription_exclusions:
        if exclusion in subscription.lower():
            return False

    scope = f"{start}{subscription}{end}"
    logger.debug("Scope: " + scope)
    return scope


def check_role_exclusions(role):
    for exclusion in azure_scope_exclusions:
        if exclusion in role:
            return False
    return True


async def audit_azure_resources(
    graph_client=None, confluence=None, args=None, credential=None
):
    query = """
authorizationresources
| where type =~ 'microsoft.authorization/roleassignments'
| extend roleDefinitionId= tolower(tostring(properties.roleDefinitionId))
| extend principalType = properties.principalType
| extend principalId = properties.principalId
| join kind = inner (
authorizationresources
| where type =~ 'microsoft.authorization/roledefinitions'
| extend roleDefinitionId = tolower(id), roleName = tostring(properties.roleName)
| where properties.type =~ 'BuiltInRole'
| project roleDefinitionId,roleName
) on roleDefinitionId
| extend scope = properties.scope
| project principalId,roleName,roleDefinitionId, scope
"""
    # query = "authorizationresources | limit 10"

    with timer("Query Resource Graph"):
        resources = query_resource_graph(query, credential=credential)
    userid_dict = {}
    subscription_dict = get_azure_subscriptions(credential=credential, dict=True)
    entraid_users = await graph_client.get_all_users()
    for user in entraid_users:
        userid_dict[user.id] = user.display_name
    ct = []

    for resource in resources:
        principalId = resource["principalId"]
        scope = subscription_translate(
            scope=resource["scope"], subscription_dict=subscription_dict
        )
        if scope and check_role_exclusions(resource["roleName"]):
            if principalId in userid_dict:
                ct.append(
                    {
                        BENUTZER: userid_dict[principalId],
                        ROLLE: resource["roleName"],
                        SCOPE: scope,
                    }
                )
            else:
                try:
                    group_members = await graph_client.get_group_members(principalId)
                except Exception:
                    logger.error(f"Cannot resolve principal UUID {principalId}")
                    group_members = None
                if group_members:
                    for group_member in group_members:
                        ct.append(
                            {
                                BENUTZER: group_member.display_name,
                                ROLLE: resource["roleName"],
                                SCOPE: scope,
                            }
                        )
                else:
                    # Not a resolvable group (service principal, orphaned or
                    # deleted principal, ...). get_group_members returns [] on
                    # 404, so without this fallback the principal would be
                    # silently dropped from the audit.
                    logger.warning(
                        f"Principal {principalId} is not a user or resolvable group"
                    )
                    ct.append(
                        {
                            BENUTZER: principalId,
                            ROLLE: resource["roleName"],
                            SCOPE: scope,
                        }
                    )
    ct = sorted(
        ct,
        key=lambda x: (x[BENUTZER], x[ROLLE]),
        reverse=False,
    )

    if args.test:
        logger.info("Test Mode: Skipping Confluence Update")
    else:
        confluence_update_page(
            confluence=confluence,
            title=confluence_audit_azure_resources_page_name,
            parent_id=confluence_page_id,
            table=ct,
            representation="storage",
            full_width=False,
            escape_table=True,
        )


async def main():
    parser = build_parser(
        prog="Audit Azure Resources Active Role Assignments",
        description="List active Azure resource role assignments that are not in PIM",
    )
    args = parser.parse_args()
    if args.test:
        logger.info("Running in Test Mode")

    graph_client = build_graph_client()
    credential = build_azure_credential()
    confluence = build_confluence()
    await audit_azure_resources(
        graph_client=graph_client,
        confluence=confluence,
        args=args,
        credential=credential,
    )


if __name__ == "__main__":
    with timer("Full Duration"):
        asyncio.run(main())
