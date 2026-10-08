# PyAutoBroca

Assistant evaluation history, upkeep evidence and a shared-format dashboard.
Broca answers which assistant needs attention, what evidence supports that, and
which evaluation would be useful next. Brain interprets; Mind tracks fixes.

## Local check-in

From this checkout, with Python 3.11+ and PyYAML installed:

```bash
python -m broca refresh --workspace /path/to/PyAutoLabs --mind /path/to/PyAutoMind --import-history --pilot
python -m broca check
python -m broca render --brain /path/to/PyAutoBrain --output dashboard.html
python -m pytest -q
```

Open the [live dashboard](https://pyautolabs.github.io/PyAutoBroca/) or the local [dashboard.html](dashboard.html). Brain must include the Broca theme registration.
The board uses the shared banner, check-in panel, navigation cards, collapsible
sections, responsive sizing, light/dark styling and clipboard behavior. Its
Update control is unavailable until an actual collection service is configured.
Rendering cached data never advances collection time.

`assistants.json` selects four assistant identities from Mind's `repos.yaml`;
it does not duplicate repository paths or remotes. `refresh` reads committed
files and git state only. It never imports assistant Python or launches models.
`--pilot` records a cheap file-inventory check per assistant, explicitly separate
from response quality. `--import-history` imports existing runner meta/score
summaries without changing source files. Missing or conflicting evidence is
reported, not discarded. A failed/partial refresh shows unknown freshness.

## Storage and comparisons

`records/<run_id>.json` is an immutable version-1 evaluation record;
`receipts/<sha256>.json` preserves each collection attempt. `latest.json` points
to the latest receipt. Re-ingesting identical records is a no-op; changed content
under the same run ID is rejected. Failed benchmark runs remain evidence.

Each record carries assistant commit, benchmark version/hash, model, harness,
environment, observation date and its precision, status, named metrics, reason
and source revision/path/hash. Unknown values are explicit nulls. Historical
abbreviated commits are resolved locally where possible. No time-of-day is
invented for date-only results. Rubric scores without explicit pass gates remain
unscored for pass/fail purposes, with their numerical score retained.

Comparisons require matching benchmark version/hash, model, harness, stack,
hardware, harness version and scorer revision. Incomplete historical provenance
means no comparable baseline. A changed assistant commit is permitted in a
comparison and separately displayed as a reason to reassess current coverage.
The assistant card shows the most conservative outcome on the latest recorded
day; date-only runs do not imply an order within that day. Trend comparisons use
earlier days only. Never interpret the latest day as coverage of every capability.

Ingest externally produced summaries with `python -m broca ingest result.json`.
See `docs/record-v1.md` for the contract. Keep bulk outputs and raw transcripts
in dedicated artifact storage; records retain references and hashes. Public
assistant repositories retain benchmark definitions and reproducible runners.
New runs should execute in an isolated checkout, with outputs retained outside
the public repo. Existing published history is not deleted or rewritten.

## Scope and privacy

The repository and dashboard are public. GitHub Actions publishes the saved
evidence at https://pyautolabs.github.io/PyAutoBroca/ on main updates or a manual
`Publish dashboard` dispatch. Publication does not collect new evidence, change
its refresh timestamp or run a model campaign. Review imported records and receipts
before committing; retain raw transcripts and private project data elsewhere. [CHECKIN.md](CHECKIN.md) is the board's portable workflow.
A broader campaign needs an explicit budget and execution environment. Project
feedback ingestion, full wiki/API drift audits and additional publication formats
are later extensions; the initial board provides inventory, historical results,
provenance, freshness and next-action guidance.
