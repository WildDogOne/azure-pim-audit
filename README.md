# azure-pim-audit

Python scripts that export Azure PIM / Entra ID role assignments and audit
active (non-PIM) assignments, then sync the results into Confluence wiki tables.
Designed to run inside Kestra flows but also runnable standalone.

## Entrypoints (run from repo root)

| Script | What it does |
| --- | --- |
| `PIM_EntraID_Roles.py` | Sync PIM-eligible Entra ID role assignments to Confluence |
| `PIM_Azure_Resources.py` | Sync PIM Azure (subscription-scope) role assignments to Confluence |
| `Audit_EntraID.py` | List active Entra ID assignments that are NOT in PIM (drift audit) |
| `Audit_Azure_Resources.py` | Same for Azure resources, via Azure Resource Graph |

All four accept `-t` / `--test` for a dry run (read Azure, skip the Confluence
write). Always use `-t` when verifying changes — there is no test suite for the
live sync, only unit tests for the diff logic (`pytest tests/`).

## Setup

1. Create a local `creds.py` from `creds.py.example` and fill in your values.
2. `pip install -r requirements.txt` (pinned; `.venv` is Python 3.14).
3. Register an Azure app with the permissions below and add a client secret.

### Config keys (`creds.py`)

- Confluence: `confluence_url`, `confluence_token`, `confluence_page_id`, and the
  four page-name keys.
- Azure: `azure_tenant_id`, `azure_client_id`, `azure_client_secret`.
- Exclusions (used by `Audit_Azure_Resources.py`):
  - `azure_subscription_exclusions` — substring match on subscription display name.
  - `azure_subscription_id_exclusions` — exact subscription IDs to skip.
  - `azure_scope_exclusions` — substring match on role name to skip.

## Permissions Needed

### Graph API (application permissions)
- GroupMember.Read.All
- RoleManagement.Read.Directory
- User.Read.All

> The original README listed these as `Application.GroupMember.Read.All` and
> `Application.RoleEligibilitySchedule.Read.Directory`. Verify the exact scopes
> against your tenant before relying on this list.

### Azure (for the resource scripts)
- Reader on the directories/subscriptions being enumerated (role eligibility
  + subscription listing + Resource Graph query).
