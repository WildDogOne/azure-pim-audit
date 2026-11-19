import asyncio

from kestra import Kestra

from creds import (
    confluence_page_id,
    confluence_audit_entraid_page_name,
)
from functions.cli import build_parser, build_graph_client, build_confluence, timer
from functions.functions import get_assignments, BENUTZER, ROLLE
from functions.confluence import confluence_update_page
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
            ct.append({BENUTZER: user, ROLLE: role})
    ct = sorted(
        ct,
        key=lambda x: (x[BENUTZER], x[ROLLE]),
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
    # Resolve all group memberships up front, one Graph call per unique group.
    group_ids = [a.principal.id for a in assignments if isinstance(a.principal, Group)]
    members_by_group = await graph_client.get_group_members_batch(group_ids)

    assignment_dict = {}

    def record(user, role_name):
        assignment_dict.setdefault(user, [])
        if not check_pim(
            user=user, role=role_name, pim_assignment_dict=pim_assignment_dict
        ):
            assignment_dict[user].append(role_name)

    for assignment in assignments:
        role_name = role_dict[assignment.role_definition_id]["display_name"]
        if isinstance(assignment.principal, Group):
            logger.debug(
                f"Resolving members of group '{assignment.principal.id}' "
                f"(role: {role_name})"
            )
            for group_member in members_by_group.get(assignment.principal.id, []):
                record(group_member.display_name, role_name)
        else:
            record(assignment.principal.display_name, role_name)

    ct = convert_to_common_table(assignment_dict)
    return ct


async def audit_entraid(graph_client=None, confluence=None, args=None):

    roles = await graph_client.get_entraid_roles()
    role_dict = format_entraid_roles(roles)
    assignments = await graph_client.get_entraid_role_assignments()

    # Get all Current EntraID Role Assignments from Azure PIM
    logger.info("Getting EntraID Role Assignments from Azure PIM")
    with timer("Load PIM Users"):
        pim_assignment_dict = await get_assignments(graph_client)

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
    parser = build_parser(
        prog="Audit EntraID Active Role Assignments",
        description="List active EntraID role assignments that are not in PIM",
    )
    args = parser.parse_args()
    if args.test:
        logger.info("Running in Test Mode")

    graph_client = build_graph_client()
    confluence = build_confluence()
    try:
        await audit_entraid(graph_client=graph_client, confluence=confluence, args=args)
    finally:
        await graph_client.close()


if __name__ == "__main__":
    with timer("Full Duration"):
        asyncio.run(main())
