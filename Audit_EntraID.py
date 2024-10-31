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
from msgraph.generated.role_management.directory.role_assignments.role_assignments_request_builder import (
    RoleAssignmentsRequestBuilder,
)
from kiota_abstractions.base_request_configuration import RequestConfiguration

from functions.msgraphapi import GraphAPI
from pprint import pprint

logger = Kestra.logger()


async def audit_entraid(graph_client=None, confluence=None, args=None):

    results = await graph_client.get_entraid_roles()
    for x in results:
        
        print(x.id)
        assignments = await graph_client.get_entraid_role_assignments(x.id)
        for y in assignments:
            pprint(y)
            break
        break
        


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
