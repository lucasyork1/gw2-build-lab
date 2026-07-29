# Contributing

This is an unofficial community data project. Contributions are welcome from players, build authors, reviewers, and tool developers.

## Choose the right path

1. **Data error:** open the “Report a data error” Issue form. Give the game build, effective patch, WvW context, source, observed value, expected value, and reproduction steps.
2. **WvW override:** first open a data-error Issue. Then propose a small edit to `data/wvw-overrides/overrides.json` with an HTTPS source, exact JSON path, prior-value guard, effective patch, reviewer, and verification status.
3. **Original build:** use the “Submit an original build” form. Include the Build Code and your own explanation of its equipment, weapons, traits, skills, runes, sigils, intended matchup, strengths, and weaknesses.
4. **Sourced build candidate:** use the “Submit a build candidate” form for a GW2Skills link or supported community page. Record missing fields as `Unknown`; do not fill them from memory or from a similar build.
5. **Stale third-party build:** use the “Report a stale build” form. Link the page; do not reproduce its guide. Identify the affected component, patch or game-build mismatch and provide your own testing notes.
6. **Patch-level verification:** compare the ArenaNet API, official patch notes, and in-game WvW tooltip or test result. Record the exact build ID, date, context, source URLs, and reviewer identity.

Prefer ArenaNet API data and official patch notes. The official wiki can be supporting evidence. MetaBattle, Snow Crows, GW2Mists, videos, and player posts are leads or community opinions—not automatically current ground truth.

## Safety and rights

Do not submit API keys, access tokens, account data, logs containing secrets, or other credentials. This project’s public data refresh uses endpoints that do not require an API key.

Do not submit copied third-party guide text or third-party images. Link to the original page and write a short, original factual summary. Only submit builds and analysis you have the right to share, and disclose relevant relationships in `conflict_of_interest`.

## Candidate review and promotion

Build data moves through one review boundary:

```text
candidate import -> generated audit/report -> maintainer review -> move to verified in a PR
```

Run a controlled community import into the candidate directory:

```text
gw2-wvw-data import-source "https://metabattle.com/wiki/Build:Example" --dataset data/normalized/current --candidate-dir data/community-builds/candidates
```

Generated imports must never write directly to
`data/community-builds/verified/`. Generate and inspect the audit and analysis,
preserve all missing fields and conflicts, and propose promotion as an explicit
pull request. The reviewer—not the importer—moves the accepted record into the
verified directory.

`publisher_claimed_current` records a source site's current-status label while
project verification is incomplete. It is not interchangeable with
`current_verified`, which requires complete ArenaNet IDs and equipment slots,
legal WvW configuration, a matching dataset game build, and no later patch
event affecting a component.

Live imports currently support `https://en.gw2skills.net` editor pages and
MetaBattle pages on `https://metabattle.com` or
`https://www.metabattle.com`. Snow Crows and GW2Mists are evidence links only
until controlled adapters are implemented. Requests reject non-HTTPS URLs,
credentials, non-default ports and off-allowlist redirects; they allow at most
2,048 URL characters, three redirects, a 10-second request timeout, and a
2 MiB uncompressed `text/html` response.

## Validation

Set up Python 3.12+, run `python -m pip install -e ".[dev]"`, then run:

```text
pytest -q
gw2-wvw-data validate --dataset data/normalized/current --sources data/provenance/sources.json
```

A passing CI check proves structural validity, not combat effectiveness. Human WvW testing and patch-level review remain necessary.
