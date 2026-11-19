from kestra import Kestra

logger = Kestra.logger()
# from functions.log_config import logger
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.subscription import SubscriptionClient
from msgraph.generated.models.group import Group
from functions.confluence import (
    get_childid,
    get_tables,
)

# Row keys must match the Confluence page headers exactly; the diff logic
# compares rows on these tuples. Define them once so a typo is a visible
# constant change rather than a silent key error or mis-diff.
BENUTZER = "Benutzer"
ROLLE = "Rolle"
SCOPE = "Scope"
ENTRAID_KEYS = (BENUTZER, ROLLE)
AZURE_KEYS = (BENUTZER, ROLLE, SCOPE)


async def get_assignments(pim):
    assignments = await pim.get_role_eligibility_schedules()

    # Resolve all group memberships up front, one Graph call per unique group.
    group_ids = [a.principal.id for a in assignments if isinstance(a.principal, Group)]
    members_by_group = await pim.get_group_members_batch(group_ids)

    assignment_dict = {}
    for assignment in assignments:
        role = assignment.role_definition.display_name
        if isinstance(assignment.principal, Group):
            logger.debug(
                f"Group: {assignment.principal.display_name} is assigned to {role}"
            )
            members = members_by_group.get(assignment.principal.id, [])
            names = [member.display_name for member in members]
        else:
            names = [assignment.principal.display_name]

        bucket = assignment_dict.setdefault(role, [])
        for name in names:
            if name not in bucket:
                bucket.append(name)
    return assignment_dict


def build_user_array(assignment_dict):
    user_roles = {}
    for role in assignment_dict:
        if privileged_role_filter(role):
            for user in assignment_dict[role]:
                if user not in user_roles:
                    user_roles[user] = [role]
                else:
                    user_roles[user].append(role)

    user_array = []
    for user in user_roles:
        for role in user_roles[user]:
            user_array.append({BENUTZER: user, ROLLE: role})
    return user_array


def get_documented_mappings(confluence, confluence_page_id, sub_page_name):
    export_page_id = get_childid(confluence, confluence_page_id, sub_page_name)
    if export_page_id:
        tables = get_tables(confluence, export_page_id)
        existing_role_mappings = tables["tables_content"][0]

        # Extract headers
        headers = existing_role_mappings[0]
        # Convert rows to dictionaries
        role_mappings = [dict(zip(headers, row)) for row in existing_role_mappings[1:]]
    else:
        role_mappings = []
        headers = []
    return role_mappings, headers


def ensure_documented_columns(headers, keys, page_name):
    """Fail loudly when an existing Confluence table is missing key columns.

    A renamed or deleted header would otherwise make every documented row look
    stale (its key columns resolve to empty strings), so the diff would silently
    delete and re-add the whole table - including any manual columns - and write
    that to the live page. An empty page (no headers) is fine and left alone.
    """
    if headers and not all(k in headers for k in keys):
        missing = [k for k in keys if k not in headers]
        raise ValueError(
            f"Confluence page '{page_name}' table is missing expected column(s) "
            f"{missing}; found headers {headers}. Refusing to sync to avoid "
            "wiping existing rows."
        )


def _row_key(row, keys):
    """Stable comparison key for a row over the given columns."""
    return tuple(row.get(k, "") for k in keys)


def diff_add(new_rows, existing_rows, headers, keys):
    """Append rows from new_rows not already present in existing_rows.

    Returns (existing_rows, changes) where changes is the list of added rows,
    or False when nothing was added.
    """
    existing_keys = {_row_key(row, keys) for row in existing_rows}
    changes = []
    for row in new_rows:
        key = _row_key(row, keys)
        if key not in existing_keys:
            for header in headers:
                row.setdefault(header, "")
            logger.info(f"New mapping: {row}")
            existing_rows.append(row)
            existing_keys.add(key)
            changes.append(row)
    return existing_rows, (changes or False)


def diff_remove(new_rows, existing_rows, keys):
    """Drop rows from existing_rows that no longer appear in new_rows.

    Comparison is on the key columns only, so extra columns (e.g. a manual
    notes column on the wiki page) do not affect the match, and identical rows
    are all kept or all removed consistently. Returns (remaining, changes).
    """
    new_keys = {_row_key(row, keys) for row in new_rows}
    changes = [row for row in existing_rows if _row_key(row, keys) not in new_keys]
    if changes:
        remaining = [row for row in existing_rows if _row_key(row, keys) in new_keys]
        for change in changes:
            logger.info(f"Removed mapping: {change}")
        return remaining, changes
    return existing_rows, False


def check_new_mappings(user_array, role_mappings, headers):
    return diff_add(user_array, role_mappings, headers, ENTRAID_KEYS)


def check_removed_mappings(user_array, role_mappings):
    return diff_remove(user_array, role_mappings, ENTRAID_KEYS)


def privileged_role_filter(role):
    privileged_groups = [
        "Application Administrator",
        "Application Developer",
        "Authentication Administrator",
        "Authentication Extensibility Administrator",
        "B2C IEF Keyset Administrator",
        "Cloud Application Administrator",
        "Cloud Device Administrator",
        "Conditional Access Administrator",
        "Directory Writers",
        "Domain Name Administrator",
        "External Identity Provider Administrator",
        "Global Administrator",
        "Global Reader",
        "Helpdesk Administrator",
        "Hybrid Identity Administrator",
        "Intune Administrator",
        "Lifecycle Workflows Administrator",
        "Partner Tier1 Support",
        "Partner Tier2 Support",
        "Password Administrator",
        "Privileged Authentication Administrator",
        "Privileged Role Administrator",
        "Security Administrator",
        "Security Operator",
        "Security Reader",
        "User Administrator",
        "AI Administrator"
    ]
    if role in privileged_groups:
        return True
    else:
        return False


def check_new_azure_resource_mappings(
        existing_role_mappings=[], new_role_mappings=[], headers=[]
):
    return diff_add(new_role_mappings, existing_role_mappings, headers, AZURE_KEYS)


def check_removed_azure_resource_mappings(
        existing_role_mappings=[], new_role_mappings=[]
):
    return diff_remove(new_role_mappings, existing_role_mappings, AZURE_KEYS)


def get_azure_resource_role_assignments(subscription_ids, credential):
    from azure.core.exceptions import HttpResponseError
    if isinstance(subscription_ids, str):
        subscription_ids = [subscription_ids]
    results = []
    failed_subscriptions = []
    for subscription_id in subscription_ids:
        try:
            scope = f"/subscriptions/{subscription_id}"
            client = AuthorizationManagementClient(credential, subscription_id)
            assignments = client.role_eligibility_schedule_instances.list_for_scope(scope)
            for assignment in assignments:
                expanded = assignment.expanded_properties
                # end_date_time = assignment.end_date_time or "permanent"
                result = {
                    "PrincipalName": expanded.principal.display_name,
                    # "PrincipalEmail": expanded.principal.email,
                    "PrincipalType": expanded.principal.type,
                    "PrincipalId": expanded.principal.id,
                    "RoleName": expanded.role_definition.display_name,
                    "RoleType": expanded.role_definition.type,
                    # "RoleId": expanded.role_definition.id,
                    # "ScopeId": expanded.scope.id,
                    "ScopeName": expanded.scope.display_name,
                    "ScopeType": expanded.scope.type,
                    # "Status": assignment.status,
                    # "createdOn": assignment.created_on,
                    # "startDateTime": assignment.start_date_time,
                    # "endDateTime": end_date_time,
                    # "updatedOn": assignment.updated_on,
                    "memberType": assignment.member_type,
                    # "id": assignment.id,
                }
                results.append(result)
        except HttpResponseError as e:
            logger.error(f"Failed to get role assignments for subscription {subscription_id}: {e.message}")
            failed_subscriptions.append(subscription_id)
        except Exception as e:
            logger.error(f"Unexpected error for subscription {subscription_id}: {str(e)}")
            failed_subscriptions.append(subscription_id)
    if failed_subscriptions:
        logger.warning(f"Failed to process {len(failed_subscriptions)} subscriptions: {', '.join(failed_subscriptions)}")
    return results


def get_azure_subscriptions(credential=None, filters=None, starts_with=None, dict=False):
    client = SubscriptionClient(credential)
    response = client.subscriptions.list()
    if dict:
        subscriptions = {}
    else:
        subscriptions = []
    for item in response:
        subscription_id = item.subscription_id
        append_subscription = False
        if starts_with:
            if isinstance(starts_with, str):
                starts_with = [starts_with]
            for x in starts_with:
                if item.display_name.lower().startswith(x.lower()):
                    append_subscription = True
        if filters:
            if isinstance(filters, str):
                filters = [filters]
            for x in filters:
                if x.lower() in item.display_name.lower():
                    append_subscription = True

        if not filters and not starts_with:
            append_subscription = True

        if append_subscription and subscription_id not in subscriptions:
            if dict:
                subscriptions[subscription_id] = item.display_name
            else:
                subscriptions.append(subscription_id)

    return subscriptions


async def build_azure_resource_assignments(
        role_assignments=None, assignment_dict=None, groups_evaluated=None, graph_client=None
):
    if assignment_dict is None:
        assignment_dict = {}
    if groups_evaluated is None:
        groups_evaluated = {}

    # Resolve all group memberships up front, one Graph call per unique group.
    # Caching the members (not the group id) lets a group assigned to several
    # scope/role pairs expand into each of them, which the old per-group-id
    # cache silently dropped after the first occurrence.
    group_ids = [
        ra["PrincipalId"]
        for ra in role_assignments
        if ra["PrincipalType"] == "Group"
    ]
    members_by_group = await graph_client.get_group_members_batch(group_ids)
    groups_evaluated.update(members_by_group)

    for role_assignment in role_assignments:
        scope = role_assignment["ScopeName"]
        role = role_assignment["RoleName"]

        if role_assignment["PrincipalType"] == "Group":
            members = members_by_group.get(role_assignment["PrincipalId"], [])
            names = [member.display_name for member in members]
        elif role_assignment["PrincipalType"] == "User":
            # Direct user principal. This branch was previously missing, so
            # users PIM-eligible at a scope directly never reached the table.
            names = [role_assignment["PrincipalName"]]
        else:
            # Service principals, managed identities, directory roles, etc.
            # are not "Benutzer" (users); skip them to keep the page to humans.
            continue

        if not names:
            continue

        bucket = assignment_dict.setdefault(scope, {}).setdefault(role, [])
        for name in names:
            if name not in bucket:
                bucket.append(name)

    return assignment_dict, groups_evaluated
