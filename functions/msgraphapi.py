from msgraph import GraphServiceClient
from kestra import Kestra

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

        result = await self.graph_client.groups.by_group_id(group_id).members.get()
        return result.value

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

    async def get_entraid_role_assignments(self, role_id):
        query_params = UnifiedRoleAssignmentItemRequestBuilder.UnifiedRoleAssignmentItemRequestBuilderGetQueryParameters(
            expand=["principal"],
        )

        request_configuration = RequestConfiguration(
            query_parameters=query_params,
        )

        result = await self.graph_client.role_management.directory.role_assignments.by_unified_role_assignment_id(
            role_id
        ).get(
            request_configuration=request_configuration
        )
        from pprint import pprint

        pprint(result)
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
