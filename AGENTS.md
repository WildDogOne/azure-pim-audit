# AGENTS.md

Python scripts that export Azure PIM / Entra ID role assignments and audit active
assignments, then sync the results into Confluence wiki tables. No package, no
build system, no CI. Unit tests exist for the diff logic only (`tests/`).

## Entrypoints (run from repo root; imports use `from functions...`)

- `PIM_EntraID_Roles.py` — sync PIM-eligible Entra ID role assignments to a Confluence page
- `PIM_Azure_Resources.py` — sync PIM Azure (subscription-scope) role assignments to Confluence
- `Audit_EntraID.py` — list active Entra ID assignments that are NOT in PIM (drift audit)
- `Audit_Azure_Resources.py` — same for Azure resources, via Azure Resource Graph

All four accept `-t` / `--test` (dry-run: read Azure, skip the Confluence write).
Always use `-t` when verifying changes. The diff logic is unit-tested with
`pytest tests/`; the live sync itself has no test beyond the `-t` dry-run.
Shared CLI plumbing (argparse, client builders, `timer` context manager) lives
in `functions/cli.py`; the four mains build clients on demand (not at import).

## Setup / config

- Requires a local `creds.py` (gitignored) copied from `creds.py.example`.
  `creds.py.example` defines all config keys the scripts import, including the
  exclusion lists used by `Audit_Azure_Resources.py`
  (`azure_subscription_exclusions`, `azure_subscription_id_exclusions`,
  `azure_scope_exclusions`).
- Requires an Azure app registration with Graph API application permissions
  (see README) plus a client secret; auth is `ClientSecretCredential`, no
  interactive login.
- `.venv` is Python 3.14 (`/usr/bin/python3.14`). Install deps with
  `pip install -r requirements.txt`.

## Non-obvious conventions

- Table rows are dicts with German keys — `Benutzer`, `Rolle`, `Scope`. These
  keys must match the Confluence page headers exactly; the diff logic in
  `check_new_mappings` / `check_removed_mappings` compares on them and would
  silently key-error or mis-diff otherwise.
- The sync scripts are diff-based: they read the existing Confluence table, add
  new rows, delete rows no longer in Azure, and only write when changes exist.
  Preserve that flow; don't turn it into a blind overwrite.
- Logging/timing/outputs go through Kestra (`from kestra import Kestra` →
  `Kestra.logger()`, `Kestra.timer`, `Kestra.outputs`); scripts are designed to
  run inside Kestra flows but also work standalone.
- Group principals are expanded to members via Graph. `GraphAPI.get_group_members`
  handles a single group (deleted groups return 404 and are skipped, not fatal);
  `get_group_members_batch` resolves many groups concurrently (one call per unique
  id) and is what the sync/audit paths now use.
- `functions/log_config.py` runs `setup_logging()` at import time (writes
  `app.log`); current scripts use Kestra logger instead and mostly don't import it.

## Dead / legacy files

`data/` and `classes/` (both empty) are legacy scratch, not part of the pipeline.
(`main.ps1`, `azure_resources.ipynb`, and `role_assignments.py` were removed.)
