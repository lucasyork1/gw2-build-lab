# GW2 Build Lab

An unofficial, community-maintained data foundation for version-aware Guild Wars 2 WvW Thief build analysis.

> Current scope: **WvW + Thief data foundation.** Natural-language build generation, Build Template decoding, third-party build import, stale-build analysis, and combat scoring are planned later layers—not features of this first milestone.

## Why this exists

Small balance changes can alter a build’s damage, survival, mobility, matchups, and equipment choices. This project keeps source-linked, game-build-specific data so future analysis can distinguish current facts from stale recommendations.

The data pipeline:

```text
ArenaNet public API
  -> immutable bilingual snapshot
  -> Thief/WvW normalization
  -> reviewed WvW-only corrections
  -> validation and semantic diff
  -> versioned JSON + SQLite release
```

It fetches English and Simplified Chinese names, tracks provenance and game build IDs, opens update pull requests instead of silently replacing data, and does not require a Guild Wars 2 API key.

## Local use

Requires Python 3.12 or newer.

```text
python -m venv .venv
python -m pip install -e ".[dev]"
pytest -q
gw2-wvw-data validate --dataset data/normalized/current
gw2-wvw-data release --dataset data/normalized/current --output dist
```

On Windows, after a current dataset exists:

```text
powershell -File scripts/verify_release.ps1
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to report a stale build or data error, propose an auditable WvW correction, or submit an original tested build.

## Source policy

ArenaNet API data and official patch notes are preferred. The official Guild Wars 2 Wiki is useful supporting evidence. MetaBattle, Snow Crows, GW2Mists, videos, and player submissions are valuable community sources, but may be outdated and are never treated as automatically current.

Automated validation proves data structure and consistency, not combat effectiveness. WvW claims still require patch-level human testing.

## Rights and affiliation

Code is MIT licensed. Project-authored schemas, rules, and original annotations use CC BY 4.0 under the exclusions in [DATA-LICENSE.md](DATA-LICENSE.md).

This is an unofficial community project and is not affiliated with, endorsed by, or sponsored by ArenaNet or NCSOFT. Guild Wars, Guild Wars 2, GW2, ArenaNet, and related marks belong to their respective owners.
