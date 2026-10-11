# Broca state feed

`render --state-output` builds Brain's shared version-1 contract using the selected
Brain checkout's `board/_state.py::build_state`. Scientist's collector and
`connect_organ.py` consume this contract without Broca-specific parsing. Identity
comes from explicit `--repository owner/repository`; `repo` in the feed is the
repository basename required by that contract. `pages_url` is independently
configured and must be an HTTPS directory. Declared identity is not access proof.

The artifact contains only rendered HTML and JSON. It never includes raw receipts,
assistant transcripts, project source or the whole checkout. Rendering does not
collect, evaluate, publish by itself, or rewrite the append-only evidence store.

## Clocks

- `updated` is the saved latest collection **attempt**, whether complete or
  incomplete. The collection row distinguishes the successful `refreshed_at`
  timestamp from a failed/incomplete attempt.
- With no receipt, v1's required timestamp uses `1970-01-01T00:00:00Z` as an
  explicit **unknown sentinel**, not an observation. The row states timestamp
  unknown and the feed cannot be green. No `valid_until` is emitted.
- `valid_until` is bounded by the attempt timestamp plus
  `collection_max_age_days` (default 30), and by the earliest expiry of any
  currently passing benchmark. Evaluation expiry uses the same UTC calendar-day
  rule as the dashboard: midnight after `evidence_max_age_days` whole days. A
  newer collection cannot extend a passing benchmark's validity. The collection
  policy remains separate from the evaluation-age policy.
- Each assistant row retains the latest benchmark's original observation date.
  A new collection cannot freshen an old evaluation. Rendering never changes any
  of these dates. No inventory timestamp or quality measurement is inferred for
  the undated guides/workspaces catalogue.

## Status meaning

The same conservative latest-day benchmark selection and `evidence_state`
classification serve HTML and JSON. Maintenance/inventory records are not
benchmark passes. Same-day failure wins over pass because day-only timestamps
cannot establish ordering.

The aggregate reports recorded failure as red; otherwise expired collection is
stale, incomplete collection or evidence needing interpretation is yellow, and
all configured assistants having current recorded passes after complete collection
is green. Missing collection, no assistants, or only never-evaluated assistants
is grey. Items preserve the distinct reasons even when one aggregate status
takes priority. Green describes recorded assistant benchmarks only; it does not
certify all communication resources or scientific correctness.

Guides, HowTo tutorials and workspaces remain an informational inventory count,
separate from assistant evaluation rows. Their projects own source and meanings.
Ears listening, Memory knowledge, Cortex science, Heart readiness and Hands
release responsibilities are unchanged. The feed contains no executable actions
and does not create a new task ledger.

Malformed/digest-mismatched current receipts, invalid records, invalid catalogue
shapes and invalid publishing configuration fail rendering. The existing Pages
check also validates historical receipts. The job validates the generated feed
before uploading the site; deployment runs only on main. Validate PR artifacts
before merge, then verify the actual HTTPS endpoint after successful deployment
before claiming a live Scientist connection.
