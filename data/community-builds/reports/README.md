# Generated build reports

Store reproducible JSON and Markdown audit/analysis output for candidate review
here. A report is generated evidence; it is not an approval and must not
overwrite its candidate input.

Before promotion, a maintainer reviews:

- Thief and WvW identity, context, and source metadata;
- missing fields, source conflicts, unknown IDs, and legality findings;
- the audit target against the current normalized dataset and relevant patches;
- every strength, weakness, risk, and improvement against its cited evidence;
- the proposed verified record diff in a pull request.

`publisher_claimed_current` means only that a publisher labels its page as
current while project verification is incomplete. `current_verified` requires
complete ArenaNet IDs and equipment slots, legal WvW configuration, a matching
dataset build, and no later relevant patch event.

Reports do not promote records. Promotion is a separate maintainer-authored pull
request that moves a reviewed candidate into `../verified/`.
