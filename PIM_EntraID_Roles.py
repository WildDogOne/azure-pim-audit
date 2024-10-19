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
    confluence_entraid_page_name,
)
from functions.confluence import confluence_update_page, style_text
from atlassian import Confluence

from functions.functions import (
    get_assignments,
    build_user_array,
    get_documented_mappings,
    check_new_mappings,
    check_removed_mappings,
)


from functions.msgraphapi import GraphAPI

# from functions.log_config import logger

logger = Kestra.logger()



async def process_entra_id(graph_client=None, confluence=None, args=None):
    
    # Get all Current EntraID Role Assignments from Azure PIM
    start_function = time.perf_counter()
    logger.info("Getting EntraID Role Assignments from Azure PIM")
    assignment_dict = await get_assignments(graph_client)
    # Convert the results to a usable table
    logger.info("Building User Array")
    user_array = build_user_array(assignment_dict)
    end_function = time.perf_counter()
    Kestra.timer('Load PIM Users', end_function - start_function)

    # Get Currently Documented Role Mappings
    start_function = time.perf_counter()
    logger.info("Getting Documented Role Mappings")
    role_mappings, headers = get_documented_mappings(
        confluence, confluence_page_id, confluence_entraid_page_name
    )
    end_function = time.perf_counter()
    Kestra.timer('Load Documented Users', end_function - start_function)

    # Check for new mappings
    start_function = time.perf_counter()
    logger.info("Checking for new mappings")
    role_mappings, new_mappings = check_new_mappings(user_array, role_mappings, headers)
    end_function = time.perf_counter()
    Kestra.timer('Check New Mappings', end_function - start_function)

    # Remove mappings that are not in the export
    start_function = time.perf_counter()
    logger.info("Checking for removed mappings")
    role_mappings, removed_mappings = check_removed_mappings(user_array, role_mappings)
    end_function = time.perf_counter()
    Kestra.timer('Check Removed Mappings', end_function - start_function)

    # Sort the mappings by user name
    start_function = time.perf_counter()
    role_mappings = sorted(
        role_mappings, key=lambda x: (x["Benutzer"], x["Rolle"]), reverse=False
    )
    if new_mappings or removed_mappings:
        logger.info("Updating Confluence Page")
        if not args.test:
            confluence_update_page(
                confluence=confluence,
                title=confluence_entraid_page_name,
                parent_id=confluence_page_id,
                table=role_mappings,
                representation="storage",
                full_width=False,
                escape_table=True,
                body_header=style_text(
                    "Achtung! Nur bestehende Einträge ergänzen, keine neue hinzufügen!<br/>Bei bedarf an neuen rechten bitte via Incident",
                    color="red",
                    bold=True,
                ),
            )
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
    Kestra.timer('Upload_To_Confluence', end_function - start_function)

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
    await process_entra_id(graph_client=graph_client, confluence=confluence, args=args)


if __name__ == "__main__":
    start = time.perf_counter()
    asyncio.run(main())
    end = time.perf_counter()
    Kestra.timer('Full Duration', end - start)