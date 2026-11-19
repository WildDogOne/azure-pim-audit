"""Tests for the diff logic that drives the Confluence sync.

These functions decide what gets added to / removed from the wiki tables, so
they are the highest-value place to have tests (there is otherwise only the
`-t` dry-run as a safety net). Run with: pytest
"""

from functions.functions import (
    check_new_mappings,
    check_removed_mappings,
    check_new_azure_resource_mappings,
    check_removed_azure_resource_mappings,
)

import asyncio
from types import SimpleNamespace

import pytest

from msgraph.generated.models.group import Group
from functions.functions import (
    get_assignments,
    build_azure_resource_assignments,
    ensure_documented_columns,
    ENTRAID_KEYS,
    AZURE_KEYS,
)
from functions.msgraphapi import GraphAPI


# --- EntraID (Benutzer + Rolle) -------------------------------------------


def test_add_new_mapping():
    existing = [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]
    new = [{"Benutzer": "Bob", "Rolle": "User Administrator"}]
    result, changes = check_new_mappings(new, existing, ["Benutzer", "Rolle"])
    assert changes == [{"Benutzer": "Bob", "Rolle": "User Administrator"}]
    assert len(result) == 2


def test_no_change_when_already_present():
    existing = [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]
    new = [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]
    result, changes = check_new_mappings(new, existing, ["Benutzer", "Rolle"])
    assert changes is False
    assert result == existing


def test_add_fills_missing_header_columns():
    # A wiki page may have extra columns (e.g. a manual notes column).
    existing = []
    new = [{"Benutzer": "Bob", "Rolle": "User Administrator"}]
    result, changes = check_new_mappings(new, existing, ["Benutzer", "Rolle", "Notiz"])
    assert result[0]["Notiz"] == ""


def test_remove_stale_mapping():
    existing = [
        {"Benutzer": "Alice", "Rolle": "Global Administrator"},
        {"Benutzer": "Bob", "Rolle": "User Administrator"},
    ]
    new = [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]
    result, changes = check_removed_mappings(new, existing)
    assert changes == [{"Benutzer": "Bob", "Rolle": "User Administrator"}]
    assert result == [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]


def test_remove_no_change():
    existing = [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]
    new = [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]
    result, changes = check_removed_mappings(new, existing)
    assert changes is False
    assert result == existing


def test_remove_duplicate_rows_are_consistent():
    """Identical rows are all kept or all removed - never a partial delete."""
    existing = [
        {"Benutzer": "Alice", "Rolle": "Global Administrator"},
        {"Benutzer": "Alice", "Rolle": "Global Administrator"},
    ]
    # Still present in the export -> both copies survive.
    result, changes = check_removed_mappings(existing[:1], existing)
    assert changes is False
    assert len(result) == 2

    # Gone from the export -> both copies removed together.
    result, changes = check_removed_mappings([], existing)
    assert len(changes) == 2
    assert result == []


def test_extra_column_does_not_affect_match():
    """Matching is on key columns only, so a differing notes column is fine."""
    existing = [{"Benutzer": "Alice", "Rolle": "Global Administrator", "Notiz": "hi"}]
    new = [{"Benutzer": "Alice", "Rolle": "Global Administrator"}]
    result, changes = check_removed_mappings(new, existing)
    assert changes is False
    assert result == existing


# --- Azure resources (Benutzer + Rolle + Scope) ---------------------------


def test_azure_add_and_remove_on_scope():
    existing = [
        {"Benutzer": "Alice", "Rolle": "Owner", "Scope": "/subscriptions/sub-a"},
    ]
    new = [
        {"Benutzer": "Alice", "Rolle": "Owner", "Scope": "/subscriptions/sub-b"},
    ]
    result, changes = check_new_azure_resource_mappings(
        existing, new, ["Benutzer", "Rolle", "Scope"]
    )
    assert changes == new
    assert len(result) == 2

    result, changes = check_removed_azure_resource_mappings(result, new)
    # sub-a entry is now stale and must be dropped.
    assert changes == [{"Benutzer": "Alice", "Rolle": "Owner", "Scope": "/subscriptions/sub-a"}]
    assert result == new


def test_azure_scope_difference_is_a_new_row():
    existing = [{"Benutzer": "Alice", "Rolle": "Owner", "Scope": "/subscriptions/sub-a"}]
    new = [{"Benutzer": "Alice", "Rolle": "Owner", "Scope": "/subscriptions/sub-b"}]
    _, changes = check_removed_azure_resource_mappings(existing, new)
    assert changes == existing


# --- build_azure_resource_assignments (expansion) -------------------------


class _Member:
    def __init__(self, name):
        self.display_name = name


class _FakeGraph:
    def __init__(self, members):
        self._members = members

    async def get_group_members_batch(self, group_ids, concurrency=5):
        return {gid: self._members.get(gid, []) for gid in group_ids if gid}


def test_direct_user_is_not_dropped():
    """Regression: direct (non-group) principals used to be silently dropped."""
    role_assignments = [
        {
            "PrincipalType": "User",
            "PrincipalId": "u1",
            "PrincipalName": "Carol",
            "ScopeName": "sub-a",
            "RoleName": "Owner",
        }
    ]
    result, _ = asyncio.run(
        build_azure_resource_assignments(role_assignments, {}, {}, _FakeGraph({}))
    )
    assert result == {"sub-a": {"Owner": ["Carol"]}}


def test_group_expands_into_every_scope_and_role():
    """Regression: a group assigned to several scope/role pairs must expand
    into each of them, not just the first occurrence."""
    role_assignments = [
        {
            "PrincipalType": "Group",
            "PrincipalId": "g1",
            "PrincipalName": "Team",
            "ScopeName": "sub-a",
            "RoleName": "Owner",
        },
        {
            "PrincipalType": "Group",
            "PrincipalId": "g1",
            "PrincipalName": "Team",
            "ScopeName": "sub-b",
            "RoleName": "Contributor",
        },
    ]
    graph = _FakeGraph({"g1": [_Member("Alice"), _Member("Bob")]})
    result, _ = asyncio.run(
        build_azure_resource_assignments(role_assignments, {}, {}, graph)
    )
    assert result["sub-a"]["Owner"] == ["Alice", "Bob"]
    assert result["sub-b"]["Contributor"] == ["Alice", "Bob"]


def test_non_user_direct_principal_is_skipped():
    """Service principals / managed identities are not 'Benutzer' and must be
    excluded from the PIM Azure page."""
    role_assignments = [
        {
            "PrincipalType": "ServicePrincipal",
            "PrincipalId": "sp1",
            "PrincipalName": "Some App",
            "ScopeName": "sub-a",
            "RoleName": "Contributor",
        }
    ]
    result, _ = asyncio.run(
        build_azure_resource_assignments(role_assignments, {}, {}, _FakeGraph({}))
    )
    assert result == {}


# --- header-column guard --------------------------------------------------


def test_ensure_documented_columns_raises_on_missing_column():
    with pytest.raises(ValueError):
        ensure_documented_columns(["Benutzer", "Notiz"], ENTRAID_KEYS, "Page")


def test_ensure_documented_columns_ok_when_present_or_empty():
    ensure_documented_columns(["Benutzer", "Rolle"], ENTRAID_KEYS, "Page")
    ensure_documented_columns(["Benutzer", "Rolle", "Scope"], AZURE_KEYS, "Page")
    # An empty page (no headers yet) is allowed - nothing to wipe.
    ensure_documented_columns([], ENTRAID_KEYS, "Page")


# --- batched group-member lookup ------------------------------------------


class _FakeGraphMembers:
    def __init__(self, members):
        self._members = members
        self.calls = 0

    async def get_group_members(self, group_id):
        self.calls += 1
        return self._members.get(group_id, [])

    # Borrow the real batch implementation and run it against this fake.
    get_group_members_batch = GraphAPI.get_group_members_batch


def test_get_group_members_batch_dedups_and_returns_dict():
    graph = _FakeGraphMembers({"g1": [_Member("Alice")]})
    result = asyncio.run(graph.get_group_members_batch(["g1", "g1", "g2"]))
    assert graph.calls == 2  # g1 fetched once, g2 once (deleted g2 -> [])
    assert set(result) == {"g1", "g2"}
    assert [m.display_name for m in result["g1"]] == ["Alice"]
    assert result["g2"] == []


# --- get_assignments on the batched path ----------------------------------


class _FakePim:
    def __init__(self, assignments, members):
        self._assignments = assignments
        self._members = members

    async def get_role_eligibility_schedules(self):
        return self._assignments

    async def get_group_members_batch(self, group_ids, concurrency=5):
        return {gid: self._members.get(gid, []) for gid in dict.fromkeys(group_ids) if gid}


def _asg(principal, role):
    return SimpleNamespace(principal=principal, role_definition=SimpleNamespace(display_name=role))


def test_get_assignments_expands_users_and_groups():
    group = Group()
    group.id = "g1"
    group.display_name = "Team"
    user = SimpleNamespace(id="u1", display_name="Carol")
    members = {"g1": [_Member("Alice"), _Member("Bob")]}
    assignments = [_asg(group, "Owner"), _asg(user, "Reader")]
    result = asyncio.run(get_assignments(_FakePim(assignments, members)))
    assert sorted(result["Owner"]) == ["Alice", "Bob"]
    assert result["Reader"] == ["Carol"]


# --- azure wrappers called by keyword (as the entrypoint does) ------------


def test_azure_wrappers_called_by_keyword():
    s1 = {"Benutzer": "A", "Rolle": "Owner", "Scope": "/subscriptions/s1"}
    s2 = {"Benutzer": "A", "Rolle": "Owner", "Scope": "/subscriptions/s2"}
    existing = [s1]
    new = [s2]
    result, changes = check_new_azure_resource_mappings(
        existing_role_mappings=existing,
        new_role_mappings=new,
        headers=["Benutzer", "Rolle", "Scope"],
    )
    # diff_add appends in place (matching the original sync behaviour).
    assert changes == [s2]
    assert len(result) == 2
    result, changes = check_removed_azure_resource_mappings(
        existing_role_mappings=result, new_role_mappings=new
    )
    assert changes == [s1]
    assert result == [s2]
