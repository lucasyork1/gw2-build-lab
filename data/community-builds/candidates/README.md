# Candidate builds

This directory is the landing area for unreviewed WvW Thief build imports.
Candidate records are evidence for review, not verified recommendations.

The supported workflow is:

```text
candidate import -> generated audit/report -> maintainer review -> move to verified in a PR
```

`gw2-wvw-data import-source` writes only to the directory supplied with
`--candidate-dir`. Use this directory explicitly when importing repository
candidates. The command never writes to `../verified/`.

```text
gw2-wvw-data import-source "https://metabattle.com/wiki/Build:Example" --dataset data/normalized/current --candidate-dir data/community-builds/candidates
```

Keep only the source URL, title, source dates and status labels, Build Code or
editor link, and explicit configuration fields. Do not add guide prose, images,
comments, ratings, or guessed values. Missing or conflicting facts remain
visible for the audit and maintainer review.

Live source imports currently allow HTTPS pages on `metabattle.com` and
`www.metabattle.com`; linked editor configurations may use
`en.gw2skills.net`. See the root README for the enforced request limits.
