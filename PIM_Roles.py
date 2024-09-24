import asyncio
import json
from msgraph.generated.models.group import Group
from creds import (
    azure_tenant_id,
    azure_client_id,
    azure_client_secret,
    confluence_page_id,
    confluence_token,
    confluence_url,
)
from functions.confluence import (
    confluence_update_page,
    style_text,
    get_childid,
    convert_to_html_table,
    get_tables,
)
from atlassian import Confluence


from pprint import pprint

from functions.msgraphapi import GraphAPI
from functions.log_config import logger


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


async def main():
    graph_client = GraphAPI(
        azure_tenant_id=azure_tenant_id,
        azure_client_id=azure_client_id,
        azure_client_secret=azure_client_secret,
    )
    confluence = Confluence(url=confluence_url, token=confluence_token)

    assignment_dict = await get_assignments(graph_client)
    user_array = build_user_array(assignment_dict)

    title = "PIM: EntraID Rollen"

    export_page_id = get_childid(confluence, confluence_page_id, title)
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

    # Sort by Username
    role_mappings = sorted(role_mappings, key=lambda x: x["Benutzer"], reverse=False)

    # Remove mappings that are not in the export
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

    confluence_update_page(
        confluence=confluence,
        title=title,
        parent_id=confluence_page_id,
        table=role_mappings,
        representation="storage",
        full_width=False,
        # body_header=body,
        # body_footer="footer",
        escape_table=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
