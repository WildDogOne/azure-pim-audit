import argparse
from datetime import datetime
from azure.identity import DefaultAzureCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.core.exceptions import HttpResponseError

from creds import (
    azure_tenant_id,
    azure_client_id,
    azure_client_secret,
    confluence_page_id,
    confluence_token,
    confluence_url,
    confluence_entraid_page_name,
)


def get_pim_azure_resource_eligible_assignment(
    tenant_id,
    subscription_id=None,
    scope=None,
    include_future_assignments=False,
    summary=False,
    at_bellow_scope=False,
):
    """
    List eligible assignments defined at the provided scope or below.

    :param tenant_id: EntraID tenant ID
    :param subscription_id: Subscription ID
    :param scope: Use scope parameter if you want to work at other scope than a subscription
    :param include_future_assignments: When enabled, will use the roleEligibilitySchedules API which also lists future assignments
    :param summary: When enabled, will return the most useful information only
    :param at_bellow_scope: Will return only the assignments defined at lower scopes
    :return: List of eligible assignments
    """
    try:
        if not scope:
            scope = f"/subscriptions/{subscription_id}"

        # Use DefaultAzureCredential for authentication
        credential = DefaultAzureCredential()
        client = AuthorizationManagementClient(credential, subscription_id)

        # Determine which API to use based on include_future_assignments
        if include_future_assignments:
            assignments = client.role_eligibility_schedules.list_for_scope(scope)
        else:
            assignments = client.role_eligibility_schedule_instances.list_for_scope(
                scope
            )

        results = []
        for assignment in assignments:
            properties = assignment.properties
            expanded = properties.expanded_properties
            end_date_time = properties.end_date_time or "permanent"

            result = {
                "PrincipalName": expanded.principal.display_name,
                "PrincipalEmail": expanded.principal.email,
                "PrincipalType": expanded.principal.type,
                "PrincipalId": expanded.principal.id,
                "RoleName": expanded.role_definition.display_name,
                "RoleType": expanded.role_definition.type,
                "RoleId": expanded.role_definition.id,
                "ScopeId": expanded.scope.id,
                "ScopeName": expanded.scope.display_name,
                "ScopeType": expanded.scope.type,
                "Status": properties.status,
                "createdOn": properties.created_on,
                "startDateTime": properties.start_date_time,
                "endDateTime": end_date_time,
                "updatedOn": properties.updated_on,
                "memberType": properties.member_type,
                "id": assignment.id,
            }

            if summary:
                result = {
                    k: v
                    for k, v in result.items()
                    if k
                    in [
                        "ScopeId",
                        "RoleName",
                        "RoleType",
                        "PrincipalId",
                        "PrincipalName",
                        "PrincipalEmail",
                        "PrincipalType",
                        "Status",
                        "startDateTime",
                        "endDateTime",
                    ]
                }

            if at_bellow_scope and len(result["ScopeId"]) <= len(scope):
                continue

            results.append(result)

        return results

    except HttpResponseError as e:
        print(f"An error occurred: {e}")
        return None


if __name__ == "__main__":

    results = get_pim_azure_resource_eligible_assignment(
        args.tenant_id,
        args.subscription_id,
        args.scope,
        args.include_future_assignments,
        args.summary,
        args.at_bellow_scope,
    )

    if results:
        for result in results:
            print(result)
    else:
        print("No results found or an error occurred.")
