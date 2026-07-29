# GW2 WvW Thief Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, versioned repository that fetches public ArenaNet API data, normalizes the Thief subset, applies reviewed WvW overrides, validates provenance, and publishes deterministic JSON and SQLite artifacts.

**Architecture:** A Python CLI performs deterministic fetch, normalization, override, validation, diff, and release stages. Human-readable JSON is the reviewed source of truth; SQLite and release bundles are generated artifacts. GitHub Actions detects game-build changes and opens review PRs, but never publishes unreviewed data.

**Tech Stack:** Python 3.12, standard library, `httpx`, `jsonschema`, `pytest`, SQLite, GitHub Actions

## Global Constraints

- Cover WvW Thief only, including core Thief and every current Thief elite specialization.
- Use stable ArenaNet IDs as primary keys.
- Keep raw snapshots separate from normalized data and WvW overrides.
- Every mutable record must identify game build, effective patch, mode, fetch time, source, and verification state.
- Never copy third-party guide prose or images.
- Do not require or persist player API keys.
- Do not publish partial, schema-invalid, or conflicting data.
- Use deterministic programs for GW2 data handling; do not send official or third-party source text to a generative model.
- Code license: MIT. Project-authored schemas, rules, and annotations: CC BY 4.0. External rights remain with their owners.

---

## File Map

```text
pyproject.toml                         package, dependencies, pytest config
src/gw2_wvw_data/__init__.py          package version
src/gw2_wvw_data/cli.py               command-line entrypoint
src/gw2_wvw_data/models.py            shared typed records and enums
src/gw2_wvw_data/io.py                canonical JSON reads/writes and hashing
src/gw2_wvw_data/api.py               ArenaNet HTTP client and retry policy
src/gw2_wvw_data/fetch.py             endpoint acquisition and snapshot manifest
src/gw2_wvw_data/normalize.py         Thief filtering and entity linkage
src/gw2_wvw_data/overrides.py         WvW override validation and application
src/gw2_wvw_data/validate.py          dataset invariants
src/gw2_wvw_data/diff.py              game-build change report
src/gw2_wvw_data/release.py           JSON bundle, SQLite, checksums
schemas/*.schema.json                 versioned public JSON Schemas
data/raw/.gitkeep                     raw snapshot root
data/normalized/.gitkeep              normalized dataset root
data/history/.gitkeep                 version diff root
data/wvw-overrides/overrides.json     reviewed WvW corrections
data/provenance/sources.json          source registry
tests/fixtures/api/*.json             small synthetic API responses
tests/fixtures/overrides/*.json       valid and invalid overrides
tests/test_*.py                       unit and integration tests
.github/workflows/check-update.yml    scheduled build detection and PR creation
.github/workflows/validate.yml        PR validation
.github/workflows/release.yml         reviewed tag release
.github/ISSUE_TEMPLATE/*.yml          structured community reports
.github/pull_request_template.md      contribution checklist
CONTRIBUTING.md                       contributor workflow
CODE_OF_CONDUCT.md                    community conduct
SECURITY.md                           key and vulnerability reporting
LICENSE                              MIT code license
DATA-LICENSE.md                       authored-data and external-rights notice
```

### Task 1: Package Skeleton and Canonical JSON I/O

**Files:**
- Create: `pyproject.toml`
- Create: `src/gw2_wvw_data/__init__.py`
- Create: `src/gw2_wvw_data/cli.py`
- Create: `src/gw2_wvw_data/models.py`
- Create: `src/gw2_wvw_data/io.py`
- Create: `tests/test_io.py`
- Create: `data/raw/.gitkeep`
- Create: `data/normalized/.gitkeep`
- Create: `data/history/.gitkeep`

**Interfaces:**
- Produces: `VerificationStatus`, `SourceRef`, `canonical_json_bytes(value)`, `write_json(path, value)`, `sha256_file(path)`
- Produces CLI command: `gw2-wvw-data --help`

- [ ] **Step 1: Write the failing canonical-output test**

```python
from gw2_wvw_data.io import canonical_json_bytes


def test_canonical_json_is_sorted_and_newline_terminated():
    assert canonical_json_bytes({"z": 1, "a": "盗贼"}) == (
        b'{\n  "a": "\xe7\x9b\x97\xe8\xb4\xbc",\n  "z": 1\n}\n'
    )
```

- [ ] **Step 2: Run the test and confirm the package is missing**

Run: `python -m pytest tests/test_io.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'gw2_wvw_data'`.

- [ ] **Step 3: Create the package metadata**

Set these exact project values in `pyproject.toml`:

```toml
[project]
name = "gw2-wvw-thief-data"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27,<1", "jsonschema>=4.23,<5"]

[project.optional-dependencies]
dev = ["pytest>=8.3,<9"]

[project.scripts]
gw2-wvw-data = "gw2_wvw_data.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: Implement shared enums and canonical I/O**

Define:

```python
class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    AUTOMATED = "automated"
    HUMAN_VERIFIED = "human_verified"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class SourceRef:
    source_type: str
    url: str
    fetched_at: str
```

Implement `canonical_json_bytes` with UTF-8, `ensure_ascii=False`, `sort_keys=True`, two-space indentation, and one trailing newline. Implement atomic `write_json` using a sibling temporary file and `Path.replace`.

- [ ] **Step 5: Add an argparse CLI with placeholder-free command registration**

Register `fetch`, `normalize`, `apply-overrides`, `validate`, `diff`, and `release` subcommands. Each handler imports its corresponding module lazily and returns its integer exit code.

- [ ] **Step 6: Run tests and CLI smoke test**

Run: `python -m pytest tests/test_io.py -v`

Expected: PASS.

Run: `python -m gw2_wvw_data.cli --help`

Expected: exit 0 and all six subcommands listed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src tests/test_io.py data
git commit -m "chore: scaffold deterministic data pipeline"
```

### Task 2: ArenaNet API Client and Versioned Raw Snapshots

**Files:**
- Create: `src/gw2_wvw_data/api.py`
- Create: `src/gw2_wvw_data/fetch.py`
- Create: `tests/test_api.py`
- Create: `tests/test_fetch.py`
- Create: `tests/fixtures/api/build.json`
- Create: `tests/fixtures/api/profession-thief.json`

**Interfaces:**
- Consumes: `write_json(path, value)`, `sha256_file(path)`
- Produces: `ArenaNetClient.get_json(path, params=None) -> object`
- Produces: `ArenaNetAPIError`
- Produces: `fetch_snapshot(client, output_root, fetched_at) -> SnapshotManifest`
- Produces CLI: `gw2-wvw-data fetch --output data/raw`

- [ ] **Step 1: Write retry and snapshot-manifest tests**

Cover these exact cases:

```python
import httpx
import pytest

from gw2_wvw_data.api import ArenaNetAPIError, ArenaNetClient


def test_client_retries_429_then_returns_json():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(200, json={"id": 204132}, request=request)

    client = ArenaNetClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )
    assert client.get_json("/v2/build") == {"id": 204132}
    assert calls == 2


def test_client_does_not_retry_404():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(404, request=request)

    client = ArenaNetClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )
    with pytest.raises(ArenaNetAPIError, match="404"):
        client.get_json("/v2/missing")
    assert calls == 1
```

Also implement `test_fetch_writes_manifest_only_after_every_endpoint_succeeds` and `test_fetch_removes_staging_directory_after_partial_failure` with a dictionary-backed fake client. The failure test must raise on the skills endpoint and assert that neither `manifest.json` nor a `.staging-*` directory remains.

- [ ] **Step 2: Run tests and confirm missing modules**

Run: `python -m pytest tests/test_api.py tests/test_fetch.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the HTTP policy**

Use base URL `https://api.guildwars2.com`. Set:

- connect timeout: 10 seconds
- read timeout: 60 seconds
- retries: 3
- retry statuses: 429, 500, 502, 503, 504
- exponential delays: 1, 2, 4 seconds
- user agent: `gw2-wvw-thief-data/0.1 (+GitHub repository URL)`

Reject non-JSON responses and payloads above 100 MiB. Do not accept an API key option in this phase.

- [ ] **Step 4: Implement staged endpoint fetching**

Fetch these public resources:

```text
/v2/build
/v2/professions/Thief?lang=en
/v2/professions/Thief?lang=zh
/v2/specializations?ids=all&lang=en
/v2/specializations?ids=all&lang=zh
/v2/traits?ids=all&lang=en
/v2/traits?ids=all&lang=zh
/v2/skills?ids=all&lang=en
/v2/skills?ids=all&lang=zh
/v2/itemstats?ids=all&lang=en
/v2/itemstats?ids=all&lang=zh
/v2/items
```

Fetch item detail IDs in batches of at most 200. Write into `data/raw/<build-id>/.staging-*`, then rename only after all required files and the manifest exist.

The manifest fields are:

```json
{
  "schema_version": 1,
  "game_build_id": 204132,
  "fetched_at": "2026-07-28T20:00:00Z",
  "api_base_url": "https://api.guildwars2.com",
  "files": [{"path": "skills.en.json", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}]
}
```

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_api.py tests/test_fetch.py -v`

Expected: PASS, including cleanup after simulated endpoint failure.

- [ ] **Step 6: Perform an opt-in live smoke test**

Run: `python -m gw2_wvw_data.cli fetch --output work/live-raw`

Expected: one complete build directory, no `.staging-*` directory, and hashes matching every manifest entry.

- [ ] **Step 7: Commit**

```bash
git add src/gw2_wvw_data/api.py src/gw2_wvw_data/fetch.py tests
git commit -m "feat: fetch versioned ArenaNet API snapshots"
```

### Task 3: Public Schemas and Thief Normalization

**Files:**
- Create: `schemas/dataset.schema.json`
- Create: `schemas/entity.schema.json`
- Create: `schemas/manifest.schema.json`
- Create: `src/gw2_wvw_data/normalize.py`
- Create: `tests/test_normalize.py`
- Create: `tests/fixtures/api/specializations.json`
- Create: `tests/fixtures/api/traits.json`
- Create: `tests/fixtures/api/skills.json`
- Create: `tests/fixtures/api/itemstats.json`
- Create: `tests/fixtures/api/items.json`

**Interfaces:**
- Consumes: a complete raw snapshot manifest
- Produces: `normalize_snapshot(snapshot_dir, output_dir) -> Dataset`
- Produces files: `profession.json`, `specializations.json`, `traits.json`, `skills.json`, `itemstats.json`, `equipment.json`, `upgrades.json`, `consumables.json`, `dataset-manifest.json`

- [ ] **Step 1: Write failing normalization tests**

Assert that normalization:

- keeps only specializations whose `profession == "Thief"`
- includes every trait referenced by those specializations
- includes profession skill IDs and Thief-only skill records
- retains stable IDs even when localized names differ
- filters items to level-80 relevant Armor, Weapon, UpgradeComponent, and Consumable records
- sorts entity arrays by integer ID
- records unresolved references instead of dropping them

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/test_normalize.py -v`

Expected: FAIL because schemas and normalizer are absent.

- [ ] **Step 3: Define the entity envelope**

Every normalized record uses:

```json
{
  "id": 123,
  "kind": "skill",
  "names": {"en": "Example", "zh": "示例"},
  "mode": "wvw",
  "game_build_id": 204132,
  "effective_patch": null,
  "source_refs": ["arenanet-api:skills:123"],
  "verification_status": "automated",
  "payload": {}
}
```

`effective_patch` is nullable for raw API facts; WvW overrides must populate it.

- [ ] **Step 4: Implement entity closure**

Build the Thief closure in this order:

1. profession record
2. profession specialization IDs
3. referenced specialization trait IDs
4. skills whose `professions` contains `Thief`
5. skills referenced by profession weapon/slot structures
6. itemstats
7. relevant equipment, upgrades, relics, runes, sigils, food, and utility consumables

Keep an `unresolved_references` array in the dataset manifest. Validation will reject non-empty unresolved references for release.

- [ ] **Step 5: Validate fixture output against JSON Schema**

Run: `python -m pytest tests/test_normalize.py -v`

Expected: PASS.

- [ ] **Step 6: Normalize the live smoke-test snapshot**

Run: `python -m gw2_wvw_data.cli normalize --snapshot work/live-raw/<build-id> --output work/live-normalized`

Expected: exit 0, deterministic sorted files, and a manifest with zero duplicate IDs.

- [ ] **Step 7: Commit**

```bash
git add schemas src/gw2_wvw_data/normalize.py tests
git commit -m "feat: normalize Thief WvW source data"
```

### Task 4: Provenance Registry and Reviewed WvW Overrides

**Files:**
- Create: `data/provenance/sources.json`
- Create: `data/wvw-overrides/overrides.json`
- Create: `schemas/override.schema.json`
- Create: `src/gw2_wvw_data/overrides.py`
- Create: `tests/test_overrides.py`
- Create: `tests/fixtures/overrides/valid.json`
- Create: `tests/fixtures/overrides/conflict.json`

**Interfaces:**
- Consumes: normalized dataset and override array
- Produces: `apply_overrides(dataset, overrides) -> AppliedDataset`
- Produces: `OverrideConflictError`
- Produces CLI: `gw2-wvw-data apply-overrides`

- [ ] **Step 1: Write failing override tests**

Test:

```python
from copy import deepcopy

import pytest

from gw2_wvw_data.overrides import OverrideConflictError, apply_overrides


def test_override_changes_only_wvw_effective_view(valid_dataset, valid_override):
    original = deepcopy(valid_dataset)
    result = apply_overrides(valid_dataset, [valid_override])
    assert result["entities"][0]["payload"]["coefficient"] == 0.8
    assert valid_dataset == original


def test_two_values_for_same_entity_path_and_patch_are_conflict(
    valid_dataset, valid_override
):
    second = {**valid_override, "value": 0.7}
    with pytest.raises(OverrideConflictError, match="entity_id=123"):
        apply_overrides(valid_dataset, [valid_override, second])
```

Add three fixture-based tests that reject a missing `effective_patch` or `source_url`, an unknown target ID, and a `previous_value` that differs from the normalized current value.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_overrides.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Define the override schema**

Use exact fields:

```json
{
  "entity_kind": "skill",
  "entity_id": 123,
  "json_pointer": "/payload/facts/0/value",
  "mode": "wvw",
  "value": 0.8,
  "previous_value": 1.25,
  "effective_patch": "2026-07-14",
  "source_url": "https://en-forum.guildwars2.com/topic/174766-game-update-notes-july-14-2026/",
  "verification_status": "human_verified",
  "notes": "Power coefficient, WvW only"
}
```

Reject non-HTTPS sources, modes other than `wvw`, missing `previous_value`, and statuses other than `human_verified`.

- [ ] **Step 4: Implement copy-on-write application**

Apply RFC 6901 JSON Pointers to a deep copy. Before setting, assert the current value equals `previous_value`; otherwise raise a conflict that prints entity ID, pointer, expected value, and actual value.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_overrides.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data/provenance data/wvw-overrides schemas/override.schema.json src/gw2_wvw_data/overrides.py tests
git commit -m "feat: add reviewed WvW override layer"
```

### Task 5: Dataset Validation and Build-to-Build Diff

**Files:**
- Create: `src/gw2_wvw_data/validate.py`
- Create: `src/gw2_wvw_data/diff.py`
- Create: `tests/test_validate.py`
- Create: `tests/test_diff.py`

**Interfaces:**
- Consumes: applied dataset
- Produces: `validate_dataset(dataset) -> list[ValidationIssue]`
- Produces: `diff_datasets(old, new) -> ChangeReport`
- Produces CLI commands: `validate`, `diff`

- [ ] **Step 1: Write failing invariant tests**

Require validation to report:

- duplicate `(kind, id)` keys
- unresolved referenced IDs
- missing source records
- invalid mode
- overrides lacking a human verification status
- an itemstat referenced by equipment but absent from itemstats
- a release manifest whose game build differs from entity records

- [ ] **Step 2: Write failing semantic-diff tests**

Given two fixture datasets, assert the report groups:

```json
{
  "added": [],
  "removed": [],
  "changed": [
    {
      "entity_kind": "skill",
      "entity_id": 123,
      "paths": ["/payload/facts/0/value"],
      "old": 1.25,
      "new": 0.8
    }
  ]
}
```

Ignore `fetched_at`-only changes.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_validate.py tests/test_diff.py -v`

Expected: FAIL during import.

- [ ] **Step 4: Implement validation with stable issue codes**

Use codes such as `duplicate_entity`, `unresolved_reference`, `missing_source`, `invalid_mode`, `unreviewed_override`, `missing_itemstat`, and `build_mismatch`. Sort issues by code, entity kind, and ID so CI output is stable.

- [ ] **Step 5: Implement field-level semantic diff**

Recursively compare mappings and arrays. Treat arrays of entity records as ID-keyed maps; treat ordered skill facts as arrays. Exclude only `/fetched_at` and file hashes from semantic comparison.

- [ ] **Step 6: Run tests and a live pipeline check**

Run: `python -m pytest tests/test_validate.py tests/test_diff.py -v`

Expected: PASS.

Run: `python -m gw2_wvw_data.cli validate --dataset work/live-normalized`

Expected: exit 0 or a nonzero exit with a complete, stable list of real unresolved-data issues to fix before Task 6.

- [ ] **Step 7: Commit**

```bash
git add src/gw2_wvw_data/validate.py src/gw2_wvw_data/diff.py tests
git commit -m "feat: validate and diff versioned datasets"
```

### Task 6: Deterministic JSON and SQLite Releases

**Files:**
- Create: `src/gw2_wvw_data/release.py`
- Create: `schemas/release-manifest.schema.json`
- Create: `tests/test_release.py`

**Interfaces:**
- Consumes: validated applied dataset
- Produces: `build_release(dataset_dir, output_dir) -> ReleaseManifest`
- Produces: `gw2-wvw-thief-data-<build>.zip`, `gw2-wvw-thief-<build>.sqlite3`, `SHA256SUMS`, `release-manifest.json`
- Produces CLI: `gw2-wvw-data release`

- [ ] **Step 1: Write failing reproducibility and parity tests**

Test that:

- two releases from identical inputs have identical file hashes
- ZIP member timestamps are fixed to `1980-01-01T00:00:00`
- SQLite row counts match JSON entity counts
- foreign-key checks return no rows
- invalid datasets produce no output directory

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_release.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Define the SQLite schema**

Create tables:

```sql
CREATE TABLE entity (
  kind TEXT NOT NULL,
  id INTEGER NOT NULL,
  name_en TEXT,
  name_zh TEXT,
  mode TEXT NOT NULL CHECK (mode = 'wvw'),
  game_build_id INTEGER NOT NULL,
  effective_patch TEXT,
  verification_status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (kind, id)
);

CREATE TABLE source (
  source_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  url TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);

CREATE TABLE entity_source (
  kind TEXT NOT NULL,
  entity_id INTEGER NOT NULL,
  source_id TEXT NOT NULL,
  PRIMARY KEY (kind, entity_id, source_id),
  FOREIGN KEY (kind, entity_id) REFERENCES entity(kind, id),
  FOREIGN KEY (source_id) REFERENCES source(source_id)
);
```

- [ ] **Step 4: Implement deterministic artifact creation**

Set SQLite pragmas explicitly, insert rows in `(kind, id)` order, run `VACUUM`, and use fixed ZIP timestamps and permissions. Write all outputs to a staging directory; rename it only after validation, parity, and checksum generation pass.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_release.py -v`

Expected: PASS.

- [ ] **Step 6: Build the first local release candidate**

Run: `python -m gw2_wvw_data.cli release --dataset work/live-normalized --output work/release`

Expected: four release files, matching checksums, and zero SQLite foreign-key violations.

- [ ] **Step 7: Commit**

```bash
git add src/gw2_wvw_data/release.py schemas/release-manifest.schema.json tests
git commit -m "feat: generate reproducible JSON and SQLite releases"
```

### Task 7: GitHub Validation, Update PR, and Release Workflows

**Files:**
- Create: `.github/workflows/validate.yml`
- Create: `.github/workflows/check-update.yml`
- Create: `.github/workflows/release.yml`
- Create: `tests/test_workflow_contracts.py`

**Interfaces:**
- Consumes: CLI commands from Tasks 1–6
- Produces: protected-branch validation status `validate-data`
- Produces: update branches named `data/game-build-<id>`
- Produces: GitHub Releases tagged `data-v<game-build-id>`

- [ ] **Step 1: Write workflow-contract tests**

Parse workflow YAML as text and assert:

- permissions default to `contents: read`
- update workflow alone receives `contents: write` and `pull-requests: write`
- release workflow triggers only on `data-v*` tags
- all workflows use Python 3.12
- validation runs `pytest` and the dataset validator
- no workflow accepts or prints a player API key

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/test_workflow_contracts.py -v`

Expected: FAIL because workflows are absent.

- [ ] **Step 3: Implement PR validation**

`validate.yml` must:

1. check out the exact commit
2. set up Python 3.12
3. install `.[dev]`
4. run `python -m pytest -q`
5. run `gw2-wvw-data validate --dataset data/normalized/current`

- [ ] **Step 4: Implement scheduled update detection**

`check-update.yml` runs daily at `17 9 * * *` UTC and by manual dispatch. It fetches into a temporary directory, compares the new build with `data/normalized/current/dataset-manifest.json`, exits without a commit when unchanged, and otherwise:

1. normalizes and validates
2. writes `data/history/<old>-to-<new>.json`
3. updates `data/normalized/current`
4. creates branch `data/game-build-<new>`
5. commits with GitHub Actions bot identity
6. opens a PR with `gh pr create`

The PR body must state that WvW overrides and patch notes require human review. Do not tag or release from this workflow.

- [ ] **Step 5: Implement reviewed tag release**

`release.yml` verifies the tag number matches the dataset game build, reruns all tests and validation, creates artifacts in `dist/`, and uploads them using `gh release create`. Any mismatch aborts before upload.

- [ ] **Step 6: Run workflow-contract tests**

Run: `python -m pytest tests/test_workflow_contracts.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows tests/test_workflow_contracts.py
git commit -m "ci: automate reviewed data updates and releases"
```

### Task 8: Community Contribution and Compliance Files

**Files:**
- Create: `.github/ISSUE_TEMPLATE/stale-build.yml`
- Create: `.github/ISSUE_TEMPLATE/data-error.yml`
- Create: `.github/ISSUE_TEMPLATE/new-build.yml`
- Create: `.github/pull_request_template.md`
- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `SECURITY.md`
- Create: `LICENSE`
- Create: `DATA-LICENSE.md`
- Create: `tests/test_community_contracts.py`

**Interfaces:**
- Produces: structured Issue fields for patch, WvW mode, source, Build Code, test context, and conflicts of interest
- Produces: explicit prohibition on secrets and copied third-party prose

- [ ] **Step 1: Write failing community-contract tests**

Assert the committed templates contain:

- `game_build`
- `effective_patch`
- `source_url`
- `build_code`
- `wvw_context`
- `testing_notes`
- `conflict_of_interest`
- warning not to submit API keys
- warning not to copy third-party guide text or images

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_community_contracts.py -v`

Expected: FAIL because files are absent.

- [ ] **Step 3: Write contribution rules**

Document the exact path for:

1. reporting data errors
2. proposing a WvW override
3. submitting an original Build
4. reporting a stale third-party Build
5. performing patch-level human verification

State that a passing CI check proves structural validity, not combat effectiveness.

- [ ] **Step 4: Add licenses and rights notice**

Use the unmodified MIT license text for code. In `DATA-LICENSE.md`, apply CC BY 4.0 only to project-authored schemas, rules, and annotations; identify ArenaNet marks/content and external sources as excluded from that grant. Link to ArenaNet's current Content Terms and require a terms recheck before the first public release.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_community_contracts.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .github/ISSUE_TEMPLATE .github/pull_request_template.md CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md LICENSE DATA-LICENSE.md tests
git commit -m "docs: establish community contribution policy"
```

### Task 9: End-to-End Acceptance and Remote-Repository Readiness

**Files:**
- Create: `tests/test_end_to_end.py`
- Create: `scripts/verify_release.ps1`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: all earlier pipeline stages
- Produces: one-command local verification via `powershell -File scripts/verify_release.ps1`
- Produces: a clean repository ready to push once GitHub is connected

- [ ] **Step 1: Write an offline end-to-end test**

Using only fixtures, run:

```text
raw fixture -> normalize -> apply overrides -> validate -> diff -> release
```

Assert zero validation issues, one expected semantic change, JSON/SQLite parity, and deterministic artifact hashes.

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/test_end_to_end.py -v`

Expected: FAIL until the test harness wires all interfaces together.

- [ ] **Step 3: Implement the PowerShell verification script**

The script must set `$ErrorActionPreference = 'Stop'` and run:

```powershell
python -m pytest -q
python -m gw2_wvw_data.cli validate --dataset data/normalized/current
python -m gw2_wvw_data.cli release --dataset data/normalized/current --output work/verification-release
```

It must not delete directories outside `work/verification-release`.

- [ ] **Step 4: Run the complete offline suite**

Run: `powershell -File scripts/verify_release.ps1`

Expected: exit 0, all tests pass, and release artifacts validate.

- [ ] **Step 5: Run one live refresh without committing automatically**

Run:

```powershell
python -m gw2_wvw_data.cli fetch --output work/final-live-raw
python -m gw2_wvw_data.cli normalize --snapshot work/final-live-raw/<build-id> --output work/final-live-normalized
python -m gw2_wvw_data.cli validate --dataset work/final-live-normalized
```

Expected: no partial directories and a complete report. Any real unresolved reference must be fixed or explicitly represented by a reviewed rule before declaring the data foundation complete.

- [ ] **Step 6: Inspect repository state**

Run: `git status --short`

Expected: no uncommitted generated artifacts; `work/` remains untracked or ignored.

- [ ] **Step 7: Commit**

```bash
git add tests/test_end_to_end.py scripts/verify_release.ps1 pyproject.toml
git commit -m "test: verify the complete data foundation"
```

- [ ] **Step 8: Connect GitHub before remote actions**

Confirm the GitHub connector lists the intended user account. Then create one public repository under that exact account, push the existing local history, enable Actions, and configure branch protection to require `validate-data`.

Do not create a repository under an inferred account name. Do not publish a Release until the current ArenaNet terms review is recorded in the repository.

---

## Plan Self-Review Result

- Spec coverage: data acquisition, normalization, WvW overrides, provenance, validation, history, deterministic releases, CI, community contribution, security, and compliance are covered.
- Deliberate exclusions: Build Code decoding, third-party adapters, stale-Build analysis, combat scoring, and natural-language mapping each require a later plan after this data foundation passes acceptance.
- Placeholder scan: no implementation placeholders remain.
- Interface consistency: all CLI stages consume the artifacts produced by the preceding stage; shared record and I/O types originate in Task 1.
