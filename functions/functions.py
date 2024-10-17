import json
from kestra import Kestra
logger = Kestra.logger()
#from functions.log_config import logger
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
            changes.extend(exported_role)
    if len(changes) < 1:
        changes = False
    return role_mappings, changes


def check_removed_mappings(user_array, role_mappings):
    changes = []
    for existing_mapping in role_mappings:
        mapped = False
        for exported_role in user_array:
            if (
                exported_role["Benutzer"] == existing_mapping["Benutzer"]
                and exported_role["Rolle"] == existing_mapping["Rolle"]
            ):
                mapped = True
                break
        if not mapped:
            print(f"Mapping not found: {existing_mapping}")
            role_mappings.remove(existing_mapping)
            changes.extend(existing_mapping)
    if len(changes) < 1:
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
