# Verified builds

This directory contains only maintainer-reviewed WvW Thief builds promoted in a
pull request. Automated imports and generated reports must never write here.

Promotion follows this boundary:

```text
candidate import -> generated audit/report -> maintainer review -> move to verified in a PR
```

A record may use `current_verified` only when all required components resolve to
ArenaNet IDs, required equipment slots are complete, WvW legality passes, the
audit target matches the normalized dataset build, and no later patch event
affects a component. A publisher's current label by itself supports only
`publisher_claimed_current`.

When a later patch or conflict undermines a verified record, open a stale-build
issue and review a corrective pull request. Do not silently edit or replace the
record.
