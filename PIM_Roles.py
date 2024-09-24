import asyncio


from creds import (
    azure_tenant_id,
    azure_client_id,
    azure_client_secret,
    confluence_page_id,
    confluence_token,
    confluence_url,
    confluence_entraid_page_name,
)
from functions.confluence import (
    confluence_update_page,
)
from atlassian import Confluence

from functions.functions import (
    get_assignments,
    build_user_array,
    get_documented_mappings,
    check_new_mappings,
    check_removed_mappings,
)
from pprint import pprint

from functions.msgraphapi import GraphAPI
from functions.log_config import logger


async def main():
    graph_client = GraphAPI(
        azure_tenant_id=azure_tenant_id,
        azure_client_id=azure_client_id,
        azure_client_secret=azure_client_secret,
    )
    confluence = Confluence(url=confluence_url, token=confluence_token)

    # Get all Current Role Assignments from Azure PIM
    assignment_dict = await get_assignments(graph_client)
    # Convert the results to a usable table
    user_array = build_user_array(assignment_dict)
    # Get Currently Documented Role Mappings
    role_mappings, headers = get_documented_mappings(
        confluence, confluence_page_id, confluence_entraid_page_name
    )
    # Check for new mappings
    role_mappings = check_new_mappings(user_array, role_mappings, headers)
    # Remove mappings that are not in the export
    role_mappings = check_removed_mappings(user_array, role_mappings)

    # Sort the mappings by user name
    role_mappings = sorted(
        role_mappings, key=lambda x: (x["Benutzer"], x["Rolle"]), reverse=False
    )
    confluence_update_page(
        confluence=confluence,
        title=confluence_entraid_page_name,
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
