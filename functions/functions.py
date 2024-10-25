import json
from kestra import Kestra

logger = Kestra.logger()
# from functions.log_config import logger
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.subscription import SubscriptionClient
from msgraph.generated.models.group import Group
from functions.confluence import (
    confluence_update_page,
    style_text,
    get_childid,
    convert_to_html_table,
    get_tables,
)


async def get_assignments(pim):
    assignment_dict = {}
    assignments = await pim.get_role_eligibility_schedules()

    for assignment in assignments:
        principal = assignment.principal
        role = assignment.role_definition.display_name
        principal_display_name = assignment.principal.display_name
        if isinstance(assignment.principal, Group):
            logger.debug(f"Group: {principal_display_name} is assigned to {role}")
            group_id = principal.id
            group_members = await pim.get_group_members(group_id)
            if len(group_members) > 0:
                for group_member in group_members:
                    member_display_name = group_member.display_name
                    if role not in assignment_dict:
                        assignment_dict[role] = [member_display_name]
                    else:
                        assignment_dict[role].append(member_display_name)
        else:
            if role not in assignment_dict:
                assignment_dict[role] = [principal_display_name]
            else:
                assignment_dict[role].append(principal_display_name)
    return assignment_dict


def build_user_array(assignment_dict):
    user_roles = {}
    for role in assignment_dict:
        if privileged_role_filter(role):
            for user in assignment_dict[role]:
                if user not in user_roles:
                    user_roles[user] = [role]
                else:
                    user_roles[user].append(role)

    user_array = []
    for user in user_roles:
        for role in user_roles[user]:
            user_array.append({"Benutzer": user, "Rolle": role})
    return user_array


def get_documented_mappings(confluence, confluence_page_id, sub_page_name):
    export_page_id = get_childid(confluence, confluence_page_id, sub_page_name)
    if export_page_id:
        tables = get_tables(confluence, export_page_id)
        existing_role_mappings = tables["tables_content"][0]

        # Extract headers
        headers = existing_role_mappings[0]
        # Convert rows to dictionaries
        role_mappings = [dict(zip(headers, row)) for row in existing_role_mappings[1:]]
    else:
        role_mappings = []
        headers = []
    return role_mappings, headers


def check_new_mappings(user_array, role_mappings, headers):
    changes = []
    for exported_role in user_array:
        mapped = False
        for existing_mapping in role_mappings:
            if (
                exported_role["Benutzer"] == existing_mapping["Benutzer"]
                and exported_role["Rolle"] == existing_mapping["Rolle"]
            ):
                mapped = True
                break
        if not mapped:
            for header in headers:
                if header not in exported_role:
                    exported_role[header] = ""
            print(f"New mapping: {exported_role}")
            role_mappings.append(exported_role)
            changes.append(exported_role)
    if len(changes) < 1:
        changes = False
    return role_mappings, changes


def check_removed_mappings(user_array, role_mappings):
    changes = []

    # Collect mappings to be removed
    for existing_mapping in [mapping for mapping in role_mappings]:
        if not any(
            exported_role["Benutzer"] == existing_mapping["Benutzer"]
            and exported_role["Rolle"] == existing_mapping["Rolle"]
            for exported_role in user_array
        ):
            print(f"Mapping not found: {existing_mapping}")
            changes.append(existing_mapping)

    # Filter out mappings that are no longer needed
    role_mappings = [mapping for mapping in role_mappings if mapping not in changes]

    if len(changes) == 0:
        changes = False

    return role_mappings, changes


def privileged_role_filter(role):
    privileged_groups = [
        "Application Administrator",
        "Application Developer",
        "Authentication Administrator",
        "Authentication Extensibility Administrator",
        "B2C IEF Keyset Administrator",
        "Cloud Application Administrator",
        "Cloud Device Administrator",
        "Conditional Access Administrator",
        "Directory Writers",
        "Domain Name Administrator",
        "External Identity Provider Administrator",
        "Global Administrator",
        "Global Reader",
        "Helpdesk Administrator",
        "Hybrid Identity Administrator",
        "Intune Administrator",
        "Lifecycle Workflows Administrator",
        "Partner Tier1 Support",
        "Partner Tier2 Support",
        "Password Administrator",
        "Privileged Authentication Administrator",
        "Privileged Role Administrator",
        "Security Administrator",
        "Security Operator",
        "Security Reader",
        "User Administrator",
    ]
    if role in privileged_groups:
        return True
    else:
        return False


def check_new_azure_resource_mappings(
    existing_role_mappings=[], new_role_mappings=[], headers=[]
):
    changes = []
    for new_role_mapping in new_role_mappings:
        mapped = False
        for existing_role_mapping in existing_role_mappings:
            if (
                new_role_mapping["Benutzer"] == existing_role_mapping["Benutzer"]
                and new_role_mapping["Rolle"] == existing_role_mapping["Rolle"]
                and new_role_mapping["Scope"] == existing_role_mapping["Scope"]
            ):
                mapped = True
                break
        if not mapped:
            for header in headers:
                if header not in new_role_mapping:
                    new_role_mapping[header] = ""
            print(f"New mapping: {new_role_mapping}")
            existing_role_mappings.append(new_role_mapping)
            changes.append(new_role_mapping)
    if len(changes) < 1:
        changes = False
    return existing_role_mappings, changes


def check_removed_azure_resource_mappings(
    existing_role_mappings=[], new_role_mappings=[]
):
    # Use list comprehension to find unmapped role mappings from existing_role_mappings.
    changes = [
        mapping
        for mapping in existing_role_mappings
        if not any(
            (
                new_mapping["Benutzer"] == mapping["Benutzer"]
                and new_mapping["Rolle"] == mapping["Rolle"]
                and new_mapping["Scope"] == mapping["Scope"]
            )
            for new_mapping in new_role_mappings
        )
    ]

    # If there are changes, remove the unmapped role mappings from existing_role_mappings.
    if changes:
        for change in changes:
            print(f"Removed mapping: {change}")
            existing_role_mappings.remove(change)

        # Return updated lists
        return existing_role_mappings, changes

    else:
        # No changes to report
        return existing_role_mappings, False


def get_azure_resource_role_assignments(subscription_ids, credential):
    if isinstance(subscription_ids, str):
        subscription_ids = [subscription_ids]
    results = []
    for subscription_id in subscription_ids:
        scope = f"/subscriptions/{subscription_id}"
        client = AuthorizationManagementClient(credential, subscription_id)
        assignments = client.role_eligibility_schedule_instances.list_for_scope(scope)
        for assignment in assignments:
            expanded = assignment.expanded_properties
            # end_date_time = assignment.end_date_time or "permanent"
            result = {
                "PrincipalName": expanded.principal.display_name,
                # "PrincipalEmail": expanded.principal.email,
                "PrincipalType": expanded.principal.type,
                "PrincipalId": expanded.principal.id,
                "RoleName": expanded.role_definition.display_name,
                "RoleType": expanded.role_definition.type,
                # "RoleId": expanded.role_definition.id,
                # "ScopeId": expanded.scope.id,
                "ScopeName": expanded.scope.display_name,
                "ScopeType": expanded.scope.type,
                # "Status": assignment.status,
                # "createdOn": assignment.created_on,
                # "startDateTime": assignment.start_date_time,
                # "endDateTime": end_date_time,
                # "updatedOn": assignment.updated_on,
                "memberType": assignment.member_type,
                # "id": assignment.id,
            }
            results.append(result)
    return results


def get_azure_subscriptions(credential=None, filters=None, starts_with=None):

    client = SubscriptionClient(credential)
    response = client.subscriptions.list()
    subscriptions = []
    for item in response:
        subscription_id = item.subscription_id
        append_subscription = False
        if starts_with:
            if isinstance(starts_with, str):
                starts_with = [starts_with]
            for x in starts_with:
                if item.display_name.lower().startswith(x.lower()):
                    append_subscription = True
        if filters:
            if isinstance(filters, str):
                filters = [filters]
            for x in filters:
                if x.lower() in item.display_name.lower():
                    append_subscription = True

        if not filters and not starts_with:
            append_subscription = True

        if append_subscription and subscription_id not in subscriptions:
            subscriptions.append(subscription_id)

    return subscriptions


async def build_azure_resource_assignments(
    role_assignments={}, assignment_dict={}, groups_evaluated=[], graph_client=None
):
    for role_assignment in role_assignments:
        if role_assignment["PrincipalType"] == "Group":
            if role_assignment["ScopeName"] not in assignment_dict:
                assignment_dict[role_assignment["ScopeName"]] = {}

            # Extract the elements for the new format
            username = None
            scope = role_assignment["ScopeName"]
            role = role_assignment["RoleName"]

            if role_assignment["PrincipalId"] not in groups_evaluated:
                group_members = await graph_client.get_group_members(
                    role_assignment["PrincipalId"]
                )
                groups_evaluated.append(role_assignment["PrincipalId"])
                if len(group_members) > 0:

                    # Add the extracted elements to the dictionary
                    if scope not in assignment_dict:
                        assignment_dict[scope] = {}

                    if role not in assignment_dict[scope]:
                        assignment_dict[scope][role] = []
                    for group_member in group_members:
                        user_display_name = group_member.display_name
                        if user_display_name not in assignment_dict[scope][role]:
                            assignment_dict[scope][role].append(user_display_name)
    return assignment_dict, groups_evaluated
