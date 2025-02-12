import asyncio
from kestra import Kestra
import argparse
import time


from creds import (
    azure_tenant_id,
    azure_client_id,
    azure_client_secret,
    confluence_page_id,
    confluence_token,
    confluence_url,
    confluence_audit_entraid_page_name,
)
from functions.functions import get_assignments
from functions.confluence import confluence_update_page
from atlassian import Confluence
from functions.msgraphapi import GraphAPI
from msgraph.generated.models.group import Group

logger = Kestra.logger()


def format_entraid_roles(roles):
    role_out = {}
    for role in roles:
        role_out[role.id] = {
            "display_name": role.display_name,
            "description": role.description,
            "is_built_in": role.is_built_in,
            "is_enabled": role.is_enabled,
            "resource_scopes": role.resource_scopes,
        }
    return role_out


def convert_to_common_table(assignment_dict):
    ct = []
    for user in assignment_dict:
        for role in assignment_dict[user]:
            ct.append({"Benutzer": user, "Rolle": role})
    ct = sorted(
        ct,
        key=lambda x: (x["Benutzer"], x["Rolle"]),
        reverse=False,
    )
    return ct


def check_pim(user=None, role=None, pim_assignment_dict=None):
    if role in pim_assignment_dict and user in pim_assignment_dict[role]:
        return True
    return False


async def audit_assignments(
    assignments=None, role_dict=None, graph_client=None, pim_assignment_dict=None
):
    assignment_dict = {}
    for assignment in assignments:
        role_name = role_dict[assignment.role_definition_id]["display_name"]
        if isinstance(assignment.principal, Group):
            group_members = await graph_client.get_group_members(
                assignment.principal.id
            )
            if len(group_members) > 0:
                for group_member in group_members:
                    member_display_name = group_member.display_name
                    if member_display_name not in assignment_dict:
                        assignment_dict[member_display_name] = []
                    if not check_pim(
                        user=member_display_name,
                        role=role_name,
                        pim_assignment_dict=pim_assignment_dict,
                    ):
                        assignment_dict[member_display_name].append(role_name)
        else:
            user = assignment.principal.display_name
            if user not in assignment_dict:
                assignment_dict[user] = []
            if not check_pim(
                user=user, role=role_name, pim_assignment_dict=pim_assignment_dict
            ):
                assignment_dict[user].append(role_name)

    ct = convert_to_common_table(assignment_dict)
    return ct


async def audit_entraid(graph_client=None, confluence=None, args=None):

    roles = await graph_client.get_entraid_roles()
    role_dict = format_entraid_roles(roles)
    assignments = await graph_client.get_entraid_role_assignments()

    # Get all Current EntraID Role Assignments from Azure PIM
    start_function = time.perf_counter()
    logger.info("Getting EntraID Role Assignments from Azure PIM")
    pim_assignment_dict = await get_assignments(graph_client)
    # Convert the results to a usable table
    logger.info("Building User Array")
    end_function = time.perf_counter()
    Kestra.timer("Load PIM Users", end_function - start_function)

    ct = await audit_assignments(
        assignments=assignments,
        role_dict=role_dict,
        graph_client=graph_client,
        pim_assignment_dict=pim_assignment_dict,
    )

    if args.test:
        logger.info("Test Mode: Skipping Confluence Update")
    else:
        confluence_update_page(
            confluence=confluence,
            title=confluence_audit_entraid_page_name,
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
    await audit_entraid(graph_client=graph_client, confluence=confluence, args=args)


if __name__ == "__main__":
    start = time.perf_counter()
    asyncio.run(main())
    end = time.perf_counter()
    Kestra.timer("Full Duration", end - start)
