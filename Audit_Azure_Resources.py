import asyncio
from kestra import Kestra
import argparse
import time
import re

from creds import (
    azure_tenant_id,
    azure_client_id,
    azure_client_secret,
    confluence_page_id,
    confluence_token,
    confluence_url,
    confluence_audit_azure_resources_page_name,
    azure_subscription_exclusions,
    azure_subscription_id_exclustions,
)
from functions.confluence import confluence_update_page
from atlassian import Confluence
from functions.msgraphapi import GraphAPI
from msgraph.generated.models.group import Group
from azure.identity import ClientSecretCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
from functions.functions import get_azure_subscriptions

logger = Kestra.logger()
from pprint import pprint

credential = ClientSecretCredential(
    azure_tenant_id, azure_client_id, azure_client_secret
)


def query_resource_graph(query=None, subscriptions=None):

    resource_graph_client = ResourceGraphClient(credential)
    if query:
        # Set up the query request
        request_options = QueryRequestOptions(result_format="objectArray")
        if not subscriptions:
            query_request = QueryRequest(query=query, options=request_options)
        else:
            query_request = QueryRequest(
                subscriptions=subscriptions, query=query, options=request_options
            )

        response = resource_graph_client.resources(query_request)
        print(response)
        return response.data


def subscription_translate(scope=None, subscription_dict=None):
    print(scope)
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
    for exclusion in azure_subscription_id_exclustions:
        if exclusion in subscription_id:
            return False
    for exclusion in azure_subscription_exclusions:
        if exclusion in subscription.lower():
            return False

    scope = f"{start}{subscription}{end}"
    logger.debug("Scope: " + scope)
    return scope


async def audit_azure_resources(graph_client=None, confluence=None, args=None):
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

    resources = query_resource_graph(query)
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
        if scope:
            if principalId in userid_dict:
                ct.append(
                    {
                        "Benutzer": userid_dict[principalId],
                        "Rolle": resource["roleName"],
                        "Scope": scope,
                    }
                )
            else:
                logger.error("User not found in EntraID")
                ct.append(
                    {
                        "Benutzer": principalId,
                        "Rolle": resource["roleName"],
                        "Scope": scope,
                    }
                )
    ct = sorted(
        ct,
        key=lambda x: (x["Benutzer"], x["Rolle"]),
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
    parser = argparse.ArgumentParser(
        prog="PIM EntraID Role Sync",
        description="Sync EntraID Role Assignments from Azure PIM to Confluence",
    )
    parser.add_argument(
        "-t",
        "--test",
        help="Dryrun the script without writing to Confluence",
        action="store_true",
    )
    args = parser.parse_args()
    if args.test:
        logger.info("Running in Test Mode")

    graph_client = GraphAPI(
        azure_tenant_id=azure_tenant_id,
        azure_client_id=azure_client_id,
        azure_client_secret=azure_client_secret,
    )

    confluence = Confluence(url=confluence_url, token=confluence_token)
    await audit_azure_resources(
        graph_client=graph_client,
        confluence=confluence,
        args=args,
    )


if __name__ == "__main__":
    start = time.perf_counter()
    asyncio.run(main())
    end = time.perf_counter()
    Kestra.timer("Full Duration", end - start)
