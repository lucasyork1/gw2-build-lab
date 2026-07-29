# GW2 WvW Thief Build Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, provenance-preserving WvW Thief pipeline that imports Build Template Codes, GW2Skills links, and controlled community pages, then audits, analyzes, compares, and reports those builds.

**Architecture:** Every input becomes one canonical JSON build record before validation. Decoders and importers never make combat judgments; the audit layer consumes the canonical build plus the versioned local dataset; the analysis layer consumes only audited builds and project-authored evidence rules. Network adapters return candidate records and never mutate verified data.

**Tech Stack:** Python 3.12+, standard library (`argparse`, `base64`, `dataclasses`, `html.parser`, `json`, `struct`, `urllib.parse`), existing `httpx` and `jsonschema`, pytest 8.3+, JSON Schema draft 2020-12.

## Global Constraints

- First release accepts only `profession: "Thief"` and `mode: "wvw"`.
- ArenaNet API data and official patch notes take precedence over community sources.
- A publisher's “up to date” label maps only to `publisher_claimed_current`, never directly to `current_verified`.
- Missing equipment, skills, traits, versions, or identifiers remain explicit `null`/missing records; no importer or analyzer may guess them.
- Build Template Codes do not contain a complete equipment template.
- GW2Skills is a configuration carrier only; current values and computed totals must come from the local versioned dataset.
- Preserve field-level provenance and retain conflicting source values without silent overwrite.
- Never copy third-party guide prose, images, comments, or full video transcripts into repository data.
- Original builds are immutable; improvements are derived variants with explicit benefits, costs, and applicability.
- Same canonical input and same dataset must produce byte-identical canonical JSON and analysis JSON.
- Network failure, malformed input, or adapter drift must not modify `data/community-builds/verified/`.
- Input URLs must use HTTPS and an allowlisted hostname; redirects must remain on the same allowlisted hostname.
- Build Code input is limited to 512 characters, URL input to 2,048 characters, fetched HTML to 2 MiB, and HTTP redirects to 3.
- Public JSON schemas must exist in both `schemas/` and `src/gw2_wvw_data/schemas/` with byte-identical contents.
- Existing data-pipeline tests and `gw2-wvw-data validate --dataset data/normalized/current` must continue to pass.

---

### Task 1: Canonical Build Contract and Repository Layout

**Files:**
- Create: `schemas/build.schema.json`
- Create: `src/gw2_wvw_data/schemas/build.schema.json`
- Create: `src/gw2_wvw_data/builds/__init__.py`
- Create: `src/gw2_wvw_data/builds/model.py`
- Create: `src/gw2_wvw_data/builds/store.py`
- Create: `tests/test_build_contract.py`
- Create: `tests/fixtures/builds/minimal-thief.json`
- Modify: `tests/test_contracts.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `BuildRecord.from_dict(value: Mapping[str, Any]) -> BuildRecord`
- Produces: `BuildRecord.to_dict() -> dict[str, Any]`
- Produces: `BuildRecord.with_updates(**changes: Any) -> BuildRecord`
- Produces: `load_build(path: str | Path) -> BuildRecord`
- Produces: `write_build(path: str | Path, build: BuildRecord) -> None`
- Produces: public schema `build.schema.json`

- [ ] **Step 1: Write failing schema and model tests**

Create tests that assert:

```python
def test_minimal_build_fixture_matches_public_schema():
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert schema_errors(value, "build.schema.json") == []


def test_build_round_trip_is_canonical(tmp_path):
    build = BuildRecord.from_dict(json.loads(FIXTURE.read_text("utf-8")))
    output = tmp_path / "build.json"
    write_build(output, build)
    assert load_build(output) == build
    assert output.read_bytes().endswith(b"\n")


def test_build_rejects_non_thief_or_non_wvw():
    value = json.loads(FIXTURE.read_text("utf-8"))
    with pytest.raises(ValueError, match="profession must be Thief"):
        BuildRecord.from_dict({**value, "profession": "Mesmer"})
    with pytest.raises(ValueError, match="mode must be wvw"):
        BuildRecord.from_dict({**value, "mode": "pve"})
```

The fixture must have this stable top-level shape:

```json
{
  "schema_version": 1,
  "build_id": "fixture-minimal-thief",
  "profession": "Thief",
  "mode": "wvw",
  "context": ["roaming"],
  "specializations": [],
  "traits": [],
  "skills": {"heal": null, "utilities": [null, null, null], "elite": null},
  "weapons": [],
  "armor": {},
  "trinkets": {},
  "runes": [],
  "relic": null,
  "infusions": [],
  "consumables": {"food": null, "utility": null},
  "assumptions": {},
  "provenance": {"sources": [], "fields": {}, "conflicts": []},
  "version_audit": {
    "status": "unverifiable",
    "game_build_id": null,
    "checked_at": null,
    "affected_components": [],
    "warnings": []
  }
}
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
pytest tests/test_build_contract.py tests/test_contracts.py -q
```

Expected: failure because `BuildRecord` and `build.schema.json` do not exist.

- [ ] **Step 3: Implement the frozen canonical model and schema**

Use frozen dataclasses for `ComponentRef`, `FieldProvenance`, `SourceRecord`, and `BuildRecord`. `BuildRecord.from_dict` must validate against the packaged schema before constructing the model. `with_updates` must return `dataclasses.replace(self, **changes)`; it must never mutate the original.

Every component reference uses:

```json
{
  "id": 13038,
  "name": "Shadowstep",
  "source": "build-code",
  "confidence": "exact"
}
```

Allowed confidence values are `exact`, `mapped`, `publisher_claimed`, and `unknown`. Allowed audit states are `current_verified`, `publisher_claimed_current`, `possibly_affected`, `stale`, `invalid`, and `unverifiable`.

`write_build` must call the existing `write_json` helper so key order and trailing newline remain deterministic.

- [ ] **Step 4: Create candidate/verified/report directories without committing generated records**

Add `.gitkeep` files under:

```text
data/community-builds/candidates/
data/community-builds/verified/
data/community-builds/reports/
```

Add only transient import staging to `.gitignore`:

```text
data/community-builds/.staging/
```

- [ ] **Step 5: Run contract tests**

Run:

```powershell
pytest tests/test_build_contract.py tests/test_contracts.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add schemas/build.schema.json src/gw2_wvw_data/schemas/build.schema.json src/gw2_wvw_data/builds tests/test_build_contract.py tests/test_contracts.py tests/fixtures/builds/minimal-thief.json data/community-builds .gitignore
git commit -m "feat: define canonical build contract"
```

---

### Task 2: Build Template Code Decoder

**Files:**
- Create: `src/gw2_wvw_data/decoders/__init__.py`
- Create: `src/gw2_wvw_data/decoders/build_code.py`
- Create: `tests/test_build_code.py`
- Create: `tests/fixtures/builds/thief-template-codes.json`
- Modify: `src/gw2_wvw_data/fetch.py`
- Modify: `tests/test_fetch.py`
- Modify: `data/normalized/current/profession.json`

**Interfaces:**
- Consumes: `BuildRecord`, `ComponentRef`
- Produces: `decode_build_code(code: str, *, dataset: Mapping[str, Any]) -> BuildRecord`
- Produces: `BuildCodeError(ValueError)`

- [ ] **Step 1: Write failing decoder tests**

Cover:

```python
VALID = "[&DQU2KywnBzkKAQAAGQEAAFgAAABXAQAAnwEAAAAAAAAAAAAAAAAAAAAAAAAEBQA2AFoALwAA]"


def test_decodes_thief_header_specializations_traits_and_land_skills(dataset):
    build = decode_build_code(VALID, dataset=dataset)
    assert build.profession == "Thief"
    assert len(build.specializations) == 3
    assert len(build.traits) == 9
    assert build.skills["heal"] is not None
    assert build.armor == {}
    assert build.version_audit["status"] == "unverifiable"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "empty"),
        ("[&not-base64]", "base64"),
        ("[&" + "A" * 600 + "]", "512"),
        ("[&AgEAWgAA]", "build template header"),
    ],
)
def test_rejects_malformed_or_oversized_codes(value, message, dataset):
    with pytest.raises(BuildCodeError, match=message):
        decode_build_code(value, dataset=dataset)
```

Add a synthetic profession-code-7 template and assert it fails with `only Thief build templates are supported`.

- [ ] **Step 2: Run decoder tests and verify failure**

Run:

```powershell
pytest tests/test_build_code.py -q
```

Expected: import failure for `gw2_wvw_data.decoders.build_code`.

- [ ] **Step 3: Implement strict binary decoding**

Normalize optional brackets, require prefix `&`, decode with `base64.b64decode(payload, validate=True)`, and require:

```text
byte 0: 0x0D build-template header
byte 1: profession code (5 for Thief)
bytes 2..7: three (specialization_id, packed_trait_choices) pairs
bytes 8..27: ten little-endian uint16 skill palette IDs
bytes 28..43: sixteen profession-specific bytes
if bytes remain, byte 44: terrestrial weapon count
next weapon_count*2 bytes: little-endian uint16 weapon type IDs
next byte: skill override count
next override_count*4 bytes: little-endian uint32 skill IDs
```

Accept the legacy exact 44-byte form as empty weapon/override arrays. Reject payloads shorter than 44 bytes, truncated dynamic arrays, and non-zero trailing bytes. Decode each packed trait choice as `(packed >> shift) & 0b11` for shifts `0`, `2`, and `4`, preserving `0` as an explicit unselected trait.

Resolve specialization and trait IDs from `specializations.json`; resolve skill palette IDs from `profession.payload.skills_by_palette`; resolve weapon type IDs through this constant:

```python
WEAPON_TYPE_IDS = {
    5: "Axe", 47: "Dagger", 54: "Pistol", 85: "Rifle",
    86: "Scepter", 89: "Staff", 90: "Sword",
    107: "Shortbow", 265: "Spear",
}
```

Unknown non-zero IDs become `ComponentRef(id=value, name=None, source="build-code", confidence="unknown")`; they do not crash decoding. Provenance for every decoded field is `build-code`.

- [ ] **Step 4: Preserve the ArenaNet skill-palette mapping**

Change both localized `/v2/professions/Thief` requests in `fetch.py` to include:

```python
params={"lang": language, "v": "latest"}
```

Add a fetch test asserting the version parameter is sent and a normalization test asserting `skills_by_palette` survives under `profession.payload`.

Because the committed dataset already represents ArenaNet Build ID `204489`, fetch `https://api.guildwars2.com/v2/professions/Thief?v=latest&lang=en`, verify `/v2/build` is still `204489`, and update only `data/normalized/current/profession.json`'s `payload.skills_by_palette` with the returned integer pairs. Keep the record's existing `game_build_id`, `fetched_at`, names, sources, and verification status unchanged. Sort pairs by palette ID before writing canonical JSON.

- [ ] **Step 5: Run decoder and data-pipeline tests**

Run:

```powershell
pytest tests/test_build_code.py tests/test_fetch.py tests/test_normalize.py -q
gw2-wvw-data validate --dataset data/normalized/current --sources data/provenance/sources.json
```

Expected: all tests pass and validation prints `[]`.

- [ ] **Step 6: Commit**

```powershell
git add src/gw2_wvw_data/decoders src/gw2_wvw_data/fetch.py data/normalized/current/profession.json tests/test_build_code.py tests/test_fetch.py tests/test_normalize.py tests/fixtures/builds/thief-template-codes.json
git commit -m "feat: decode thief build template codes"
```

---

### Task 3: Safe GW2Skills Importer

**Files:**
- Create: `src/gw2_wvw_data/importers/__init__.py`
- Create: `src/gw2_wvw_data/importers/http.py`
- Create: `src/gw2_wvw_data/importers/js_literal.py`
- Create: `src/gw2_wvw_data/importers/gw2skills.py`
- Create: `tests/test_import_http.py`
- Create: `tests/test_js_literal.py`
- Create: `tests/test_gw2skills.py`
- Create: `tests/fixtures/importers/gw2skills-thief.html`

**Interfaces:**
- Consumes: `BuildRecord`, `decode_build_code`
- Produces: `SafeHttpClient.get_text(url: str, *, allowed_hosts: frozenset[str]) -> HttpDocument`
- Produces: `parse_js_literal(text: str) -> Any`
- Produces: `import_gw2skills(url: str, *, dataset: Mapping[str, Any], client: SafeHttpClient) -> BuildRecord`
- Produces: `ImportError(ValueError)`

- [ ] **Step 1: Write failing safe-fetch and literal-parser tests**

The HTTP tests must use `httpx.MockTransport` and assert:

```python
@pytest.mark.parametrize("url", [
    "http://en.gw2skills.net/editor/?abc",
    "https://example.com/editor/?abc",
    "https://user:pass@en.gw2skills.net/editor/?abc",
])
def test_safe_client_rejects_disallowed_urls(url):
    with pytest.raises(ImportError):
        client.get_text(url, allowed_hosts=frozenset({"en.gw2skills.net"}))


def test_safe_client_rejects_cross_host_redirect():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://evil.example/payload"},
            request=request,
        )
    )
    client = SafeHttpClient(transport=transport)
    with pytest.raises(ImportError, match="redirect host"):
        client.get_text(
            "https://en.gw2skills.net/editor/?abc",
            allowed_hosts=frozenset({"en.gw2skills.net"}),
        )
```

The literal parser must accept only strings, integers, booleans, `null`, arrays, and objects with quoted-string or identifier keys. It must reject property access, function calls, comments, template strings, floats, duplicate keys, and input deeper than 32 containers.

- [ ] **Step 2: Run importer foundation tests and verify failure**

Run:

```powershell
pytest tests/test_import_http.py tests/test_js_literal.py -q
```

Expected: imports fail.

- [ ] **Step 3: Implement bounded HTTP and the non-evaluating JS-literal parser**

`SafeHttpClient` must use `httpx.Client(follow_redirects=False, timeout=10.0)`, perform at most three explicit redirects, require `text/html`, stream at most 2 MiB, and never accept cookies from caller input.

`parse_js_literal` must be a cursor-based recursive-descent parser. Do not use `eval`, `exec`, Node, a browser, or a JavaScript engine.

- [ ] **Step 4: Write failing GW2Skills extraction tests**

Use the checked-in HTML fixture containing:

```javascript
E = new BuildEditor({
  version: "9.1.4",
  balance: "2026/06/02 rev. 1",
  preload: {
    qlink: "PaABwihrlNw6YXsNGJm2XnNVA-DyYYhoHLCRoGaXhEYCkZE0bJY7VBaGwyGoC-e",
    chatlink: "DQU2OywnByoKAQAAGQEAAFcBAABYAAAAnwEAAAAAAAAAAAAAAAAAAAAAAAA=",
    mode: "wvw",
    profession: 6,
    weapon: [13,9,9,11],
    equipment: {
      weapon: {},
      armor: {},
      trinket: {},
      buff: {"food": 544, "utility": 38},
      relic: 323
    }
  }
});
```

Assert the importer extracts the `preload` object, uses `chatlink` for traits/skills, maps all explicitly present equipment slots, records site version/balance metadata, and rejects fixture variants with `mode: "pve"` or a non-Thief profession.

- [ ] **Step 5: Implement GW2Skills preload extraction and ID mapping**

Find the `new BuildEditor(` call, scan balanced delimiters while respecting quoted strings, parse only its object literal, and select `preload`. Map the fixed GW2Skills slots:

```python
ARMOR_SLOTS = ("helm", "shoulders", "coat", "gloves", "leggings", "boots")
TRINKET_SLOTS = ("back", "amulet", "earring1", "earring2", "ring1", "ring2")
WEAPON_SLOTS = ("w11", "w12", "w21", "w22")
```

The first number in each `item: [site_id, quality]`, `up`, `inf`, `buff`, and `relic` tuple is a GW2Skills site-local ID, not an ArenaNet ID. Preserve it as:

```json
{
  "id": "gw2skills:290",
  "name": null,
  "source": "gw2skills",
  "confidence": "publisher_claimed"
}
```

Only replace it with an ArenaNet ID when an explicit, tested mapping table exists. Do not infer by name or slot. Store the raw editor URL and the extracted site revision as source metadata.

- [ ] **Step 6: Run GW2Skills tests**

Run:

```powershell
pytest tests/test_import_http.py tests/test_js_literal.py tests/test_gw2skills.py -q
```

Expected: all pass without live network access.

- [ ] **Step 7: Commit**

```powershell
git add src/gw2_wvw_data/importers tests/test_import_http.py tests/test_js_literal.py tests/test_gw2skills.py tests/fixtures/importers/gw2skills-thief.html
git commit -m "feat: import gw2skills build configurations"
```

---

### Task 4: Controlled Community Source Adapters

**Files:**
- Create: `src/gw2_wvw_data/importers/community.py`
- Create: `src/gw2_wvw_data/importers/metabattle.py`
- Create: `tests/test_metabattle.py`
- Create: `tests/fixtures/importers/metabattle-thief.html`

**Interfaces:**
- Consumes: `SafeHttpClient`, `import_gw2skills`, `decode_build_code`
- Produces: `CommunityCandidate`
- Produces: `import_source(url: str, *, dataset: Mapping[str, Any], client: SafeHttpClient) -> CommunityCandidate`
- Produces: `MetaBattleAdapter.extract(document: HttpDocument) -> CommunityCandidate`

- [ ] **Step 1: Write failing MetaBattle adapter tests**

Assert the fixture produces only:

```python
assert candidate.source_name == "MetaBattle"
assert candidate.mode == "wvw"
assert candidate.context == ("roaming",)
assert candidate.profession == "Thief"
assert candidate.publisher_status == "publisher_claimed_current"
assert candidate.editor_urls == (
    "https://en.gw2skills.net/editor/"
    "?PaABwihrlNw6YXsNGJm2XnNVA-DyYYhoHLCRoGaXhEYCkZE0bJY7VBaGwyGoC-e",
)
assert candidate.guide_text is None
assert candidate.comments == ()
```

Test missing date, missing editor/build code, wrong mode, wrong profession, multiple conflicting editor links, malformed HTML, and an unsupported Snow Crows/GW2Mists URL. Unsupported hosts must return a stable `unsupported source adapter` error rather than performing a request.

- [ ] **Step 2: Run adapter tests and verify failure**

Run:

```powershell
pytest tests/test_metabattle.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement minimal HTML metadata extraction**

Use `html.parser.HTMLParser`, not CSS-selector dependencies. Capture title, page URL, explicit mode/profession/context labels, published/updated date text, publisher status label, Build Code, and GW2Skills URLs. Discard guide paragraphs, images, ratings prose, and comments.

When fields disagree, populate `CommunityCandidate.conflicts` and do not choose a winner. The adapter may call the GW2Skills importer only after candidate metadata extraction succeeds.

- [ ] **Step 4: Run adapter tests**

Run:

```powershell
pytest tests/test_metabattle.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/gw2_wvw_data/importers/community.py src/gw2_wvw_data/importers/metabattle.py tests/test_metabattle.py tests/fixtures/importers/metabattle-thief.html
git commit -m "feat: add controlled community build import"
```

---

### Task 5: Completeness, Legality, and Version Audit

**Files:**
- Create: `src/gw2_wvw_data/audit/__init__.py`
- Create: `src/gw2_wvw_data/audit/index.py`
- Create: `src/gw2_wvw_data/audit/build.py`
- Create: `src/gw2_wvw_data/audit/version.py`
- Create: `schemas/build-audit.schema.json`
- Create: `src/gw2_wvw_data/schemas/build-audit.schema.json`
- Create: `tests/test_build_audit.py`
- Create: `tests/fixtures/builds/patch-events.json`
- Modify: `tests/test_contracts.py`

**Interfaces:**
- Consumes: canonical `BuildRecord` and normalized dataset
- Produces: `DatasetIndex.from_dataset(dataset: Mapping[str, Any]) -> DatasetIndex`
- Produces: `audit_build(build: BuildRecord, *, index: DatasetIndex, patch_events: Sequence[PatchEvent], checked_at: str) -> BuildAudit`
- Produces: `BuildAudit.to_dict() -> dict[str, Any]`

- [ ] **Step 1: Write failing audit tests**

Cover:

```python
def test_build_code_only_is_legal_but_equipment_incomplete(
    build_code_only, dataset_index
):
    audit = audit_build(
        build_code_only,
        index=dataset_index,
        patch_events=[],
        checked_at="2026-07-28T23:00:00Z",
    )
    assert audit.legality == "legal"
    assert "armor.helm" in audit.missing_fields
    assert audit.status == "unverifiable"


def test_publisher_current_never_becomes_verified_without_full_resolution(
    publisher_claimed_build, dataset_index
):
    audit = audit_build(
        publisher_claimed_build,
        index=dataset_index,
        patch_events=[],
        checked_at="2026-07-28T23:00:00Z",
    )
    assert audit.status == "publisher_claimed_current"


def test_patch_after_source_marks_affected_components(
    complete_build, dataset_index, patch_events
):
    audit = audit_build(
        complete_build,
        index=dataset_index,
        patch_events=patch_events,
        checked_at="2026-07-28T23:00:00Z",
    )
    assert audit.status == "possibly_affected"
    assert audit.affected_components[0].component_id == 13038


def test_unknown_component_is_unverifiable(unknown_component_build, dataset_index):
    audit = audit_build(
        unknown_component_build,
        index=dataset_index,
        patch_events=[],
        checked_at="2026-07-28T23:00:00Z",
    )
    assert audit.status == "unverifiable"


def test_removed_component_is_invalid(removed_component_build, dataset_index):
    audit = audit_build(
        removed_component_build,
        index=dataset_index,
        patch_events=[],
        checked_at="2026-07-28T23:00:00Z",
    )
    assert audit.status == "invalid"
```

Also test illegal specialization/trait pairings, duplicate land utilities, unavailable weapon types, six rune slots, exact armor/trinket slot completeness, two weapon sets, missing relic, missing food/utility, and deterministic warning order.

- [ ] **Step 2: Run audit tests and verify failure**

Run:

```powershell
pytest tests/test_build_audit.py tests/test_contracts.py -q
```

Expected: audit modules and schemas are missing.

- [ ] **Step 3: Implement indexed deterministic checks**

`DatasetIndex` must index entities by `(kind, id)`, specialization trait tiers, profession weapon availability, skill palette, and source/effective-patch metadata once per analysis.

Status precedence:

```text
invalid
stale
unverifiable
possibly_affected
current_verified
publisher_claimed_current
```

Use `publisher_claimed_current` only when the publisher makes that claim and project verification is incomplete. Use `current_verified` only when every required component has an ArenaNet ID, all required equipment slots are complete, legality passes, the dataset build matches the audit target, and no later patch event affects a component.

- [ ] **Step 4: Run audit tests**

Run:

```powershell
pytest tests/test_build_audit.py tests/test_contracts.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/gw2_wvw_data/audit schemas/build-audit.schema.json src/gw2_wvw_data/schemas/build-audit.schema.json tests/test_build_audit.py tests/fixtures/builds/patch-events.json tests/test_contracts.py
git commit -m "feat: audit build legality and freshness"
```

---

### Task 6: Evidence Rules, Capability Analysis, and Comparison

**Files:**
- Create: `data/analysis-rules/thief-wvw-v1.json`
- Create: `schemas/analysis-rules.schema.json`
- Create: `schemas/build-analysis.schema.json`
- Create: `src/gw2_wvw_data/schemas/analysis-rules.schema.json`
- Create: `src/gw2_wvw_data/schemas/build-analysis.schema.json`
- Create: `src/gw2_wvw_data/analysis/__init__.py`
- Create: `src/gw2_wvw_data/analysis/rules.py`
- Create: `src/gw2_wvw_data/analysis/build.py`
- Create: `src/gw2_wvw_data/analysis/compare.py`
- Create: `tests/test_build_analysis.py`
- Create: `tests/test_build_compare.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**
- Consumes: `BuildRecord`, `BuildAudit`, `DatasetIndex`, validated rule JSON
- Produces: `load_rules(path: str | Path) -> RuleSet`
- Produces: `analyze_build(build: BuildRecord, audit: BuildAudit, *, index: DatasetIndex, rules: RuleSet) -> BuildAnalysis`
- Produces: `compare_builds(left: BuildRecord, right: BuildRecord) -> BuildComparison`

- [ ] **Step 1: Write failing rule and analysis tests**

Rules have this exact shape:

```json
{
  "schema_version": 1,
  "ruleset_id": "thief-wvw-v1",
  "dimensions": [
    "burst_damage",
    "sustained_damage",
    "survival_recovery",
    "condition_cleanse",
    "control_interrupt",
    "mobility_disengage",
    "stealth_reset",
    "operation_difficulty"
  ],
  "rules": [
    {
      "rule_id": "shadowstep-mobility",
      "when": {"component_id": 13038},
      "effects": [{"dimension": "mobility_disengage", "delta": 1}],
      "evidence": [{"component_id": 13038, "field": "payload"}],
      "claim": "Shadowstep contributes a mobility and disengage option."
    }
  ]
}
```

Test that invalid dimensions, missing evidence, duplicate rule IDs, or deltas outside `-2..2` fail schema validation.

Assert every emitted strength, weakness, and improvement has at least one evidence reference; incomplete equipment lowers confidence to `low` for affected dimensions; no numeric overall score exists.

- [ ] **Step 2: Run analysis tests and verify failure**

Run:

```powershell
pytest tests/test_build_analysis.py tests/test_build_compare.py tests/test_contracts.py -q
```

Expected: missing modules and schemas.

- [ ] **Step 3: Implement five-band deterministic analysis**

Start each dimension at band 3 (`medium`), apply matching deltas, clamp to `1..5`, and expose labels `very_low`, `low`, `medium`, `high`, `very_high`. Sort matching rules by `rule_id`; sort evidence by `(component_kind, component_id, field)`.

If required fields for a rule are missing, skip the delta and append a confidence reason. Never infer a component from the build title or source prose.

Improvements are predefined project-authored substitutions in the same rules file. Each has `replace`, `with`, `benefit`, `cost`, `applies_when`, and evidence. Applying one creates a derived build ID `<original-build-id>--<improvement-id>` and never mutates the original.

- [ ] **Step 4: Implement structural comparison**

`compare_builds` must report ordered additions, removals, and replacements for specializations, traits, skills, weapons, armor, trinkets, runes, relic, infusions, and consumables. It must not claim a combat benefit; benefit/cost text comes only from an explicit improvement rule.

- [ ] **Step 5: Run analysis tests**

Run:

```powershell
pytest tests/test_build_analysis.py tests/test_build_compare.py tests/test_contracts.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add data/analysis-rules schemas/analysis-rules.schema.json schemas/build-analysis.schema.json src/gw2_wvw_data/schemas src/gw2_wvw_data/analysis tests/test_build_analysis.py tests/test_build_compare.py tests/test_contracts.py
git commit -m "feat: analyze and compare audited thief builds"
```

---

### Task 7: CLI Commands and Deterministic JSON/Markdown Reports

**Files:**
- Create: `src/gw2_wvw_data/builds/service.py`
- Create: `src/gw2_wvw_data/builds/report.py`
- Create: `tests/test_build_cli.py`
- Create: `tests/test_build_report.py`
- Modify: `src/gw2_wvw_data/cli.py`

**Interfaces:**
- Consumes: all prior public interfaces
- Produces: `analyze`, `import-source`, and `compare` CLI modules through the existing dispatcher
- Produces: `render_markdown(build: BuildRecord, audit: BuildAudit, analysis: BuildAnalysis) -> str`
- Produces: `analyze_input(*, build_code: str | None, gw2skills_url: str | None, dataset_path: Path, rules_path: Path, client: SafeHttpClient | None = None) -> AnalysisBundle`

- [ ] **Step 1: Write failing CLI and report tests**

Test:

```powershell
gw2-wvw-data analyze --build-code "<code>" --dataset data/normalized/current --json out.json --markdown out.md
gw2-wvw-data analyze --gw2skills-url "<url>" --dataset data/normalized/current --json out.json --markdown out.md
gw2-wvw-data import-source "<url>" --dataset data/normalized/current --candidate-dir candidates
gw2-wvw-data compare build-a.json build-b.json --json comparison.json --markdown comparison.md
```

Use dependency injection or recorded HTML fixtures; the test suite must not perform live HTTP.

Assert:

- exactly one of `--build-code` and `--gw2skills-url` is required for `analyze`;
- output files are not created when validation fails;
- imports write only to the caller-selected candidate directory;
- a second identical run produces byte-identical JSON and Markdown;
- Markdown includes identity, completeness, version status, legality, equipment, eight capability dimensions, strengths, weaknesses, risks, improvements, evidence, and sources;
- Markdown renders missing values as `Unknown`, not as guessed equipment.

- [ ] **Step 2: Run CLI/report tests and verify failure**

Run:

```powershell
pytest tests/test_build_cli.py tests/test_build_report.py -q
```

Expected: CLI commands are absent.

- [ ] **Step 3: Implement service orchestration and atomic output**

The service must:

```text
input -> canonical BuildRecord -> BuildAudit -> BuildAnalysis -> AnalysisBundle
```

Write JSON/Markdown to sibling temporary files, then replace final outputs only after both render successfully. The canonical build, audit, and analysis must all be present in JSON output.

- [ ] **Step 4: Add commands to the dispatcher**

Extend `COMMAND_MODULES`:

```python
"analyze": "builds.service",
"import-source": "builds.service",
"compare": "builds.service",
```

`builds.service.main(argv)` must inspect the first argument as its operation so the existing dispatcher remains backward compatible.

- [ ] **Step 5: Run CLI/report and regression tests**

Run:

```powershell
pytest tests/test_build_cli.py tests/test_build_report.py tests/test_end_to_end.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add src/gw2_wvw_data/builds/service.py src/gw2_wvw_data/builds/report.py src/gw2_wvw_data/cli.py tests/test_build_cli.py tests/test_build_report.py
git commit -m "feat: expose build analysis commands"
```

---

### Task 8: Seed Corpus, Community Workflow, Documentation, and Full Verification

**Files:**
- Create: `data/community-builds/candidates/README.md`
- Create: `data/community-builds/verified/README.md`
- Create: `data/community-builds/reports/README.md`
- Create: `tests/fixtures/community-builds/seed-manifest.json`
- Create: `tests/test_seed_builds.py`
- Modify: `.github/ISSUE_TEMPLATE/stale-build.yml`
- Modify: `.github/ISSUE_TEMPLATE/submit-build.yml`
- Modify: `CONTRIBUTING.md`
- Modify: `README.md`
- Modify: `docs/PROJECT-STATE.md`

**Interfaces:**
- Consumes: the full importer/audit/analysis service
- Produces: documented candidate-to-verified workflow and a seven-architecture offline acceptance corpus

- [ ] **Step 1: Add the seven-sample manifest and failing acceptance test**

The fixture manifest must contain exactly these architecture IDs:

```json
[
  "daredevil-power-sd",
  "daredevil-celestial-sa-axe-pistol",
  "daredevil-power-scepter",
  "daredevil-sa-dagger-pistol",
  "deadeye-sa-rifle",
  "specter-celestial-scepter",
  "core-pistol-dagger-condition"
]
```

Each entry points to a checked-in Build Code, GW2Skills HTML fixture, or MetaBattle HTML fixture plus its expected specialization and weapon architecture. The acceptance test must parse all seven offline, assert Thief/WvW, run audit and analysis, and validate every JSON result. A Snow Crows Support Specter fixture may be present only with context `zerg_reference`; it must never appear in the seven roaming IDs.

- [ ] **Step 2: Run seed acceptance test and verify failure**

Run:

```powershell
pytest tests/test_seed_builds.py -q
```

Expected: fixture manifest or referenced fixtures are absent.

- [ ] **Step 3: Add sanitized source fixtures and make acceptance pass**

Fixtures may retain only minimal facts allowed by the design: title, source URL, dates/status labels, Build Code/editor link, and explicit configuration fields. Do not retain guide prose, images, comments, or full pages.

If a source cannot be resolved to a complete current configuration, keep the sample `unverifiable` and assert its missing/conflict report. Do not manufacture equipment to satisfy the test.

- [ ] **Step 4: Update contributor and operator documentation**

Document:

```text
candidate import -> generated audit/report -> maintainer review -> move to verified in a PR
```

Include examples for all four CLI operations, the difference between `publisher_claimed_current` and `current_verified`, supported hosts, network limits, and the rule that generated candidate imports never write to verified data.

Update `docs/PROJECT-STATE.md` with completed inputs, commands, limitations, current ArenaNet Build ID captured at release time, and the next approved milestone boundary.

- [ ] **Step 5: Run full verification**

Run:

```powershell
python -m pip install -e ".[dev]"
pytest -q
gw2-wvw-data validate --dataset data/normalized/current --sources data/provenance/sources.json
git diff --check
```

Expected: all tests pass, validation exits `0`, and `git diff --check` prints nothing.

- [ ] **Step 6: Commit**

```powershell
git add data/community-builds tests/fixtures/community-builds tests/test_seed_builds.py .github/ISSUE_TEMPLATE CONTRIBUTING.md README.md docs/PROJECT-STATE.md
git commit -m "docs: complete build analysis workflow"
```
