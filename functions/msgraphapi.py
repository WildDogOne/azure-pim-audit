from msgraph import GraphServiceClient
from kestra import Kestra
import asyncio

logger = Kestra.logger()
from msgraph.generated.role_management.directory.role_eligibility_schedules.role_eligibility_schedules_request_builder import (
    RoleEligibilitySchedulesRequestBuilder,
)
from msgraph.generated.groups.item.members.count.count_request_builder import (
    CountRequestBuilder,
)
from msgraph.generated.role_management.directory.role_assignments.role_assignments_request_builder import (
    RoleAssignmentsRequestBuilder,
)
from kiota_abstractions.base_request_configuration import RequestConfiguration
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from azure.identity.aio import ClientSecretCredential
from msgraph.generated.role_management.directory.role_assignments.item.unified_role_assignment_item_request_builder import (
    UnifiedRoleAssignmentItemRequestBuilder,
)


class GraphAPI:
    def __init__(
        self, azure_tenant_id=None, azure_client_id=None, azure_client_secret=None
    ):
        self.azure_tenant_id = azure_tenant_id
        self.azure_client_id = azure_client_id
        self.azure_client_secret = azure_client_secret
        self._auth()

    def _auth(self):
        self.credential = ClientSecretCredential(
            self.azure_tenant_id, self.azure_client_id, self.azure_client_secret
        )
        self.scopes = ["https://graph.microsoft.com/.default"]
        self.graph_client = GraphServiceClient(self.credential, scopes=self.scopes)

    async def get_role_eligibility_schedules(self):

        query_params = RoleEligibilitySchedulesRequestBuilder.RoleEligibilitySchedulesRequestBuilderGetQueryParameters(
            select=["principalId", "roleDefinitionId"],
            expand=["roleDefinition", "principal"],
            filter="",
        )

        request_configuration = RequestConfiguration(
            query_parameters=query_params,
        )
        schedules = []
        logger.debug("Getting first page of role eligibility schedules")
        result = await self.graph_client.role_management.directory.role_eligibility_schedules.get(
            request_configuration=request_configuration
        )
        schedules.extend(result.value)
        # Pagination if next_link is present
        while result.odata_next_link:
            logger.debug("Getting next page of role eligibility schedules")
            result = await self.graph_client.role_management.directory.role_eligibility_schedules.with_url(
                result.odata_next_link
            ).get(
                request_configuration=request_configuration
            )
            schedules.extend(result.value)
        return schedules

    async def get_group_members(self, group_id):

        request_configuration = RequestConfiguration()
        request_configuration.headers.add("ConsistencyLevel", "eventual")

        try:
            result = await self.graph_client.groups.by_group_id(group_id).members.get()
            return result.value
        except ODataError as e:
            if e.response_status_code == 404:
                logger.warning(
                    f"Group '{group_id}' not found (likely deleted); "
                    "skipping its members"
                )
                return []
            raise

    async def get_group_members_batch(self, group_ids, concurrency=5):
        """Resolve members for many groups concurrently, de-duplicated.

        Returns {group_id: [members]}. A deleted group yields an empty list
        (see get_group_members). Replaces the previous one-await-per-group
        loop, which serialised N Graph round-trips.
        """
        unique_ids = list(dict.fromkeys(gid for gid in group_ids if gid))
        if not unique_ids:
            return {}

        semaphore = asyncio.Semaphore(concurrency)

        async def _fetch(group_id):
            async with semaphore:
                return group_id, await self.get_group_members(group_id)

        results = await asyncio.gather(*(_fetch(gid) for gid in unique_ids))
        return dict(results)

    async def get_entraid_roles(self):

        result = (
            await self.graph_client.role_management.directory.role_definitions.get()
        )
        roles = []
        roles.extend(result.value)
        # Pagination if next_link is present
        while result.odata_next_link:
            logger.debug("Getting next page of role eligibility schedules")
            result = await self.graph_client.role_management.directory.role_definitions.with_url(
                result.odata_next_link
            ).get()
            roles.extend(result.value)
        return roles

    async def get_entraid_role_assignments(self):
        query_params = UnifiedRoleAssignmentItemRequestBuilder.UnifiedRoleAssignmentItemRequestBuilderGetQueryParameters(
            expand=["principal"],
        )

        request_configuration = RequestConfiguration(
            query_parameters=query_params,
        )

        result = await self.graph_client.role_management.directory.role_assignments.get(
            request_configuration=request_configuration
        )

        role_assignments = []
        role_assignments.extend(result.value)
        while result.odata_next_link:
            logger.debug("Getting next page of role eligibility schedules")
            result = await self.graph_client.role_management.directory.role_assignments.with_url(
                result.odata_next_link
            ).get(
                request_configuration=request_configuration
            )
            role_assignments.extend(result.value)
        return role_assignments

    async def get_all_users(self):
        users = []
        logger.debug("Getting first page of all users")
        result = await self.graph_client.users.get()
        users.extend(result.value)
        # Pagination if next_link is present
        while result.odata_next_link:
            logger.debug("Getting next page of all users")
            result = await self.graph_client.users.with_url(
                result.odata_next_link
            ).get()
            users.extend(result.value)
        return users

    async def get_all_groups(self):
        groups = []
        logger.debug("Getting first page of all groups")
        result = await self.graph_client.groups.get()
        groups.extend(result.value)
        while result.odata_next_link:
            logger.debug("Getting next page of all groups")
            result = await self.graph_client.groups.with_url(
                result.odata_next_link
            ).get()
            groups.extend(result.value)
        return groups
