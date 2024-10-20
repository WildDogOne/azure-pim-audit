from functions.msgraphapi import GraphAPI
import asyncio
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
    azure_tenant_root,
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


async def main():
    logger.info("Getting Azure Resource Role Assignments")
    role_assignments = get_azure_resource_role_assignments(
        azure_tenant_root, credential
    )

    logger.info("Writing Assignments into a common format")
    assignment_dict = {}
    groups_evaluated = []
    assignment_dict, groups_evaluated = await build_azure_resource_assignments(
        role_assignments=role_assignments,
        assignment_dict=assignment_dict,
        groups_evaluated=groups_evaluated,
        graph_client=graph_client,
    )
    new_role_mappings = convert_to_common_table(assignment_dict)

    logger.info("Getting existing Azure Resource Role Mappings")
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

    logger.info("Updating Confluence Page")
    if new_mappings or removed_mappings:
        confluence_update_page(
            confluence=confluence,
            title=confluence_azure_resource_page_name,
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


if __name__ == "__main__":
    start = time.perf_counter()
    asyncio.run(main())
    end = time.perf_counter()
    Kestra.timer("Full Duration", end - start)
