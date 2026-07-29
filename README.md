# GW2 Build Lab

An unofficial, community-maintained data foundation for version-aware Guild Wars 2 WvW Thief build analysis.

> Current scope: **WvW + Thief.** The project now decodes Build Template Codes, imports controlled GW2Skills and MetaBattle inputs, audits completeness/legality/version state, and emits evidence-backed analysis. It does not generate builds from natural language or calculate an overall combat score.

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

It fetches English and Simplified Chinese names, tracks provenance and game build IDs, opens update pull requests instead of silently replacing data, and does not require a Guild Wars 2 API key. Community inputs follow a separate review path:

```text
candidate import -> generated audit/report -> maintainer review -> move to verified in a PR
```

## Local use

Requires Python 3.12 or newer.

```text
python -m venv .venv
python -m pip install -e ".[dev]"
pytest -q
gw2-wvw-data validate --dataset data/normalized/current
gw2-wvw-data release --dataset data/normalized/current --output dist
```

Analyze a Build Template Code:

```text
gw2-wvw-data analyze --build-code "[&...]" --dataset data/normalized/current --json out/build.json --markdown out/build.md
```

Analyze a GW2Skills editor link:

```text
gw2-wvw-data analyze --gw2skills-url "https://en.gw2skills.net/editor/?..." --dataset data/normalized/current --json out/build.json --markdown out/build.md
```

Import a supported community page into a caller-selected candidate directory:

```text
gw2-wvw-data import-source "https://metabattle.com/wiki/Build:Example" --dataset data/normalized/current --candidate-dir data/community-builds/candidates
```

Compare two canonical build JSON files structurally:

```text
gw2-wvw-data compare build-a.json build-b.json --json out/comparison.json --markdown out/comparison.md
```

Generated candidate imports never write to
`data/community-builds/verified/`. A maintainer promotes a reviewed candidate
only through a pull request.

On Windows, after a current dataset exists:

```text
powershell -File scripts/verify_release.ps1
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to report a stale build or data error, propose an auditable WvW correction, or submit an original tested build.

## Source policy

ArenaNet API data and official patch notes are preferred. The official Guild Wars 2 Wiki is useful supporting evidence. MetaBattle, Snow Crows, GW2Mists, videos, and player submissions are valuable community sources, but may be outdated and are never treated as automatically current.

The live importer currently allowlists `en.gw2skills.net`,
`metabattle.com`, and `www.metabattle.com`. Snow Crows and GW2Mists do
not yet have controlled adapters. Network requests require HTTPS and the default
HTTPS port, reject URL credentials and cross-host redirects, and are limited to
2,048 URL characters, three redirects, a 10-second timeout, and a 2 MiB
uncompressed HTML body.

`publisher_claimed_current` means the publisher calls a page current but the
project has not completed verification. `current_verified` requires complete
ArenaNet component IDs and equipment, legal WvW configuration, a matching
dataset build, and no later relevant patch event.

Automated validation proves data structure and consistency, not combat effectiveness. WvW claims still require patch-level human testing.

## Rights and affiliation

Code is MIT licensed. Project-authored schemas, rules, and original annotations use CC BY 4.0 under the exclusions in [DATA-LICENSE.md](DATA-LICENSE.md).

This is an unofficial community project and is not affiliated with, endorsed by, or sponsored by ArenaNet or NCSOFT. Guild Wars, Guild Wars 2, GW2, ArenaNet, and related marks belong to their respective owners.
