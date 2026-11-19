import asyncio

from kestra import Kestra

from creds import (
    confluence_page_id,
    confluence_azure_resource_page_name,
)
from functions.cli import (
    build_parser,
    build_graph_client,
    build_confluence,
    build_azure_credential,
    timer,
)
from functions.confluence import confluence_update_page, style_text

from functions.functions import (
    get_documented_mappings,
    ensure_documented_columns,
    check_new_azure_resource_mappings,
    check_removed_azure_resource_mappings,
    get_azure_resource_role_assignments,
    build_azure_resource_assignments,
    get_azure_subscriptions,
    AZURE_KEYS,
    BENUTZER,
    ROLLE,
    SCOPE,
)

logger = Kestra.logger()


def convert_to_common_table(assignment_dict):
    ct = []
    for scope, roles in assignment_dict.items():
        for role in roles:
            for user in roles[role]:
                ct.append({BENUTZER: user, SCOPE: scope, ROLLE: role})
    return ct


async def process_azure_resources(
    graph_client=None, confluence=None, args=None, credential=None
):
    logger.info("Getting Azure Subscriptions")
    with timer("Loading Subscriptions"):
        subscriptions = get_azure_subscriptions(
            credential=credential  # , filters=["-v-", "_v_"], starts_with=["p-", "t-"]
        )

    logger.info("Getting Azure Resource Role Assignments")
    with timer("Loading Role Assignments"):
        role_assignments = get_azure_resource_role_assignments(subscriptions, credential)

    logger.info("Writing Assignments into a common format")
    with timer("Writing into common format"):
        assignment_dict, _ = await build_azure_resource_assignments(
            role_assignments=role_assignments,
            assignment_dict={},
            groups_evaluated={},
            graph_client=graph_client,
        )
        new_role_mappings = convert_to_common_table(assignment_dict)

    logger.info("Getting existing Azure Resource Role Mappings")
    with timer("Comparing with existing documentation"):
        existing_role_mappings, headers = get_documented_mappings(
            confluence, confluence_page_id, confluence_azure_resource_page_name
        )
        ensure_documented_columns(
            headers, AZURE_KEYS, confluence_azure_resource_page_name
        )

        logger.info("Checking for changes in Azure Resource Role Mappings")
        role_mappings, new_mappings = check_new_azure_resource_mappings(
            existing_role_mappings=existing_role_mappings,
            new_role_mappings=new_role_mappings,
            headers=headers,
        )

        logger.info("Checking for removed Azure Resource Role Mappings")
        role_mappings, removed_mappings = check_removed_azure_resource_mappings(
            existing_role_mappings=role_mappings, new_role_mappings=new_role_mappings
        )

        logger.debug("Sorting the table")
        role_mappings = sorted(
            role_mappings,
            key=lambda x: (x[BENUTZER], x[SCOPE], x[ROLLE]),
            reverse=False,
        )

    logger.info("Updating Confluence Page")
    with timer("Updating Confluence"):
        if new_mappings or removed_mappings:
            if not args.test:
                confluence_update_page(
                    confluence=confluence,
                    title=confluence_azure_resource_page_name,
                    parent_id=confluence_page_id,
                    table=role_mappings,
                    representation="storage",
                    full_width=False,
                    escape_table=True,
                    body_header=style_text(
                        "Achtung! Nur bestehende Einträge ergänzen, keine neue hinzufügen!<br/>Bei Bedarf an neuen rechten bitte via Incident",
                        color="red",
                        bold=True,
                    ),
                )
            logger.info("Confluence Page Updated")
            Kestra.outputs(
                {
                    "status": "Changes Synchronised",
                    "new_mappings": new_mappings,
                    "removed_mappings": removed_mappings,
                }
            )
        else:
            logger.info("No changes detected")
            Kestra.outputs({"status": "No changes detected"})


async def main():
    parser = build_parser(
        prog="PIM Azure Resource Role Sync",
        description="Sync Azure Resource Role Assignments from Azure PIM to Confluence",
    )
    args = parser.parse_args()
    if args.test:
        logger.info("Running in Test Mode")

    graph_client = build_graph_client()
    credential = build_azure_credential()
    confluence = build_confluence()

    try:
        await process_azure_resources(
            graph_client=graph_client,
            confluence=confluence,
            args=args,
            credential=credential,
        )
    finally:
        await graph_client.close()
        credential.close()


if __name__ == "__main__":
    with timer("Full Duration"):
        asyncio.run(main())
