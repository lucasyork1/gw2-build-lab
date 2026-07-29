from gw2_wvw_data.validate import validate_dataset


def _entity(entity_id, *, kind="skill", build=204132, mode="wvw", sources=None):
    return {
        "id": entity_id,
        "kind": kind,
        "names": {"en": str(entity_id), "zh": str(entity_id)},
        "mode": mode,
        "game_build_id": build,
        "effective_patch": None,
        "fetched_at": "2026-07-28T20:00:00Z",
        "source_refs": sources or [f"arenanet-api:{kind}s:{entity_id}"],
        "verification_status": "automated",
        "payload": {},
    }


def _valid_dataset():
    return {
        "profession": _entity("Thief", kind="profession"),
        "skills": [_entity(1)],
        "itemstats": [_entity(584, kind="itemstat")],
        "equipment": [
            {
                **_entity(1000, kind="equipment"),
                "payload": {"details": {"infix_upgrade": {"id": 584}}},
            }
        ],
        "manifest": {
            "schema_version": 1,
            "game_build_id": 204132,
            "fetched_at": "2026-07-28T20:00:00Z",
            "mode": "wvw",
            "files": [
                "profession.json",
                "skills.json",
                "itemstats.json",
                "equipment.json",
            ],
            "unresolved_references": [],
        },
        "applied_overrides": [],
    }


def test_valid_dataset_has_no_issues():
    assert validate_dataset(_valid_dataset(), source_ids={"arenanet-api"}) == []


def test_validation_reports_stable_issue_codes():
    dataset = _valid_dataset()
    dataset["skills"].append(_entity(1))
    dataset["skills"][0]["mode"] = "pve"
    dataset["skills"][0]["game_build_id"] = 999
    dataset["skills"][0]["source_refs"] = ["missing-source:skills:1"]
    dataset["manifest"]["unresolved_references"] = [
        {"kind": "trait", "id": 10, "referenced_by": "specialization:1"}
    ]
    dataset["equipment"][0]["payload"]["details"]["infix_upgrade"]["id"] = 9999
    dataset["applied_overrides"] = [
        {"entity_kind": "skill", "entity_id": 1, "verification_status": "automated"}
    ]

    issues = validate_dataset(dataset, source_ids={"arenanet-api"})

    assert [issue.code for issue in issues] == [
        "build_mismatch",
        "duplicate_entity",
        "invalid_mode",
        "missing_itemstat",
        "missing_source",
        "schema_invalid",
        "schema_invalid",
        "unresolved_reference",
        "unreviewed_override",
    ]


def test_validation_detects_manifest_mode_mismatch():
    dataset = _valid_dataset()
    dataset["manifest"]["mode"] = "pvp"

    issues = validate_dataset(dataset, source_ids={"arenanet-api"})

    assert [(issue.code, issue.entity_kind) for issue in issues] == [
        ("invalid_mode", "manifest"),
        ("schema_invalid", "manifest"),
    ]


def test_validation_rejects_entity_that_breaks_public_schema():
    dataset = _valid_dataset()
    dataset["skills"][0]["verification_status"] = "trusted_by_magic"

    issues = validate_dataset(dataset, source_ids={"arenanet-api"})

    assert [(issue.code, issue.entity_kind, issue.entity_id) for issue in issues] == [
        ("schema_invalid", "skill", "1")
    ]
