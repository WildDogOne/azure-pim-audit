import asyncio
import json
from msgraph.generated.models.group import Group
from creds import azure_tenant_id, azure_client_id, azure_client_secret, confluence_page_id, confluence_token, confluence_url
from functions.confluence import confluence_update_page, style_text, get_childid, convert_to_html_table
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



async def main():
    graph_client = GraphAPI(
    azure_tenant_id=azure_tenant_id,
    azure_client_id=azure_client_id,
    azure_client_secret=azure_client_secret,
    )
    assignment_dict = await get_assignments(graph_client)
    user_roles = {}
    for role in assignment_dict:
        for user in assignment_dict[role]:
            if user not in user_roles:
                user_roles[user] = [role]
            else:
                user_roles[user].append(role)

    user_array = []
    for user in user_roles:
        user_array.append({"user": user, "roles": user_roles[user]})
    pprint(user_array)
    """confluence_child_page_id = get_childid(
        confluence=confluence, confluence_page_id=confluence_page_id, sub_page_name=title
    )"""

    confluence = Confluence(url=confluence_url, token=confluence_token)

    body = ""

    for user in user_array:
        body += f"<h2>{user["user"]}</h2>"
        roles = []
        for role in user["roles"]:
            roles.append({"Role Name": role, "Begründung": ""})
        body += convert_to_html_table(roles)
    confluence_update_page(
        confluence=confluence,
        title="Role Export",
        parent_id=confluence_page_id,
        #table=user_roles,
        representation="storage",
        full_width=False,
        body_header=body,
        # body_footer="footer",
        escape_table=True,
    )


    pprint(user_roles)


if __name__ == "__main__":
    asyncio.run(main())
