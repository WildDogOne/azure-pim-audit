import asyncio
import json
from msgraph.generated.models.group import Group
from creds import azure_tenant_id, azure_client_id, azure_client_secret

from pprint import pprint

from classes.msgraphapi import GraphAPI


async def get_assignments(pim):
    assignment_dict = {}
    assignments = await pim.get_role_eligibility_schedules()

    for assignment in assignments:
        principal = assignment.principal
        role = assignment.role_definition.display_name
        principal_display_name = assignment.principal.display_name

        if isinstance(assignment.principal, Group):
            print(f"Group: {principal_display_name} is assigned to {role}")
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
            # print(f"Role: {role}, Principal: {principal}")
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

    pprint(assignment_dict)


if __name__ == "__main__":
    asyncio.run(main())
