from functions.msgraphapi import GraphAPI
import asyncio
import argparse
from kestra import Kestra
import time

logger = Kestra.logger()
from creds import (
    azure_tenant_id,
    azure_client_id,
    azure_client_secret,
    confluence_page_id,
    confluence_token,
    confluence_url,
    confluence_azure_resource_page_name,
)
from azure.identity import ClientSecretCredential
from azure.identity import AzureCliCredential
from functions.confluence import confluence_update_page, style_text
from atlassian import Confluence

from functions.functions import (
    get_documented_mappings,
    check_new_azure_resource_mappings,
    check_removed_azure_resource_mappings,
    get_azure_resource_role_assignments,
    build_azure_resource_assignments,
    get_azure_subscriptions,
)

credential = ClientSecretCredential(
    azure_tenant_id, azure_client_id, azure_client_secret
)

graph_client = GraphAPI(
    azure_tenant_id=azure_tenant_id,
    azure_client_id=azure_client_id,
    azure_client_secret=azure_client_secret,
)
confluence = Confluence(url=confluence_url, token=confluence_token)


def convert_to_common_table(assignment_dict):
    ct = []
    for scope, roles in assignment_dict.items():
        for role in roles:
            for user in roles[role]:
                ct.append({"Benutzer": user, "Scope": scope, "Rolle": role})
    return ct


async def process_azure_resources(graph_client=None, confluence=None, args=None):
    logger.info("Getting Azure Subscriptions")
    start_function = time.perf_counter()
    subscriptions = get_azure_subscriptions(
        credential=credential#, filters=["-v-", "_v_"], starts_with=["p-", "t-"]
    )
    end_function = time.perf_counter()
    Kestra.timer("Loading Subscriptions", end_function - start_function)

    logger.info("Getting Azure Resource Role Assignments")
    start_function = time.perf_counter()
    role_assignments = get_azure_resource_role_assignments(subscriptions, credential)
    end_function = time.perf_counter()
    Kestra.timer("Loading Role Assignments", end_function - start_function)

    logger.info("Writing Assignments into a common format")
    start_function = time.perf_counter()
    assignment_dict = {}
    groups_evaluated = []
    assignment_dict, groups_evaluated = await build_azure_resource_assignments(
        role_assignments=role_assignments,
        assignment_dict=assignment_dict,
        groups_evaluated=groups_evaluated,
        graph_client=graph_client,
    )
    new_role_mappings = convert_to_common_table(assignment_dict)
    end_function = time.perf_counter()
    Kestra.timer("Writing into common format", end_function - start_function)

    logger.info("Getting existing Azure Resource Role Mappings")
    start_function = time.perf_counter()
    existing_role_mappings, headers = get_documented_mappings(
        confluence, confluence_page_id, confluence_azure_resource_page_name
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
        key=lambda x: (x["Benutzer"], x["Scope"], x["Rolle"]),
        reverse=False,
    )
    end_function = time.perf_counter()
    Kestra.timer("Comparing with existing documentation", end_function - start_function)

    logger.info("Updating Confluence Page")
    start_function = time.perf_counter()
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
    end_function = time.perf_counter()
    Kestra.timer("Updating Confluence", end_function - start_function)


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

    await process_azure_resources(
        graph_client=graph_client, confluence=confluence, args=args
    )


if __name__ == "__main__":
    start = time.perf_counter()
    asyncio.run(main())
    end = time.perf_counter()
    Kestra.timer("Full Duration", end - start)
