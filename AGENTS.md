# GW2 Build Lab Codex Guidance

## Start every task

Before planning or changing code:

1. Read `README.md`.
2. Read `docs/PROJECT-STATE.md`.
3. Read the latest relevant file under `docs/superpowers/specs/`.
4. Read the matching implementation plan under `docs/superpowers/plans/` when one exists.
5. Check the current branch and `git status`.

## Current product scope

- Game: Guild Wars 2
- Mode: WvW
- Profession: Thief
- Current milestone: complete Build import, version audit, strengths/weaknesses analysis, and evidence-backed improvement suggestions

Do not expand to PvE, sPvP, automatic YouTube discovery, or natural-language Build generation without a separately approved design.

## Data and analysis rules

- Prefer ArenaNet API data and official patch notes.
- Treat MetaBattle, Snow Crows, GW2Mists, YouTube, and player submissions as community evidence, not automatic truth.
- Never convert a publisher's “up to date” label directly into `current_verified`.
- Do not guess missing equipment, skills, traits, or version information.
- Preserve field-level provenance and distinguish extracted facts from project analysis.
- Do not copy third-party guide prose, images, or full video transcripts into the repository.
- Keep original Builds immutable; store improvements as derived variants with explicit trade-offs.

## Git and verification

- Work on a non-`main` branch and submit changes through a Pull Request.
- Do not bypass the protected `main` branch or the required `validate-data` check.
- Preserve unrelated user changes.
- Run the narrow relevant tests during development and the full validation required by the implementation plan before completion.
- Update `docs/PROJECT-STATE.md` when a milestone, supported input, important limitation, or operating procedure changes.

