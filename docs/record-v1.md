# Evaluation record v1

All fields below are required. Unknown provenance is null, never a guessed value.
The `assistant` must appear in `assistants.json`; `run_id` is an immutable identifier
containing letters, digits, hyphens or underscores. JSON is UTF-8, no NaN/Infinity.

```json
{
  "schema_version": 1,
  "run_id": "autofit_assistant-example-001",
  "assistant": "autofit_assistant",
  "kind": "benchmark",
  "observed_at": "2026-10-01",
  "date_precision": "day",
  "assistant_sha": null,
  "benchmark": {"id": "example", "version": "1", "sha256": null},
  "model": null,
  "harness": null,
  "environment": {"stack": {}, "hardware": {}, "harness_version": null, "scorer_revision": null},
  "status": "unscored",
  "metrics": {"score": null, "wall_seconds": null, "cost_usd": null, "interventions": null},
  "reason": "Example only; not a measurement",
  "source": {
    "revision": "0000000000000000000000000000000000000000",
    "path": "benchmarks/runs/example/meta.yaml",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  }
}
```

Replace example hashes with real evidence before ingestion. The validator checks
structure and formatting, not whether a claimed source was truly measured.
`kind` is `benchmark` or `maintenance`; `status` is `passed`, `failed` or
`unscored`. `date_precision: second` requires an aware ISO timestamp with seconds;
`day` preserves a source's date-only precision. Future observations are rejected.
Metrics are finite nonnegative numbers or null. Keep each outcome dimension
separate; no combined assistant quality score is calculated.

`source.revision` is the full source commit; `source.path` is repository-relative.
Historical imports hash UTF-8 `git show` meta.yaml text, newline, then score.json
text (both stripped of trailing whitespace by the git reader; absent score = `{}`).
The inventory pilot hashes canonical JSON of its checks, assistant commit and
observation timestamp. Source provenance is fixed at first import; retries reuse
that record only if the source digest is identical. Changed evidence under the
same ID is a visible conflict, requiring a new run ID and an explanation.

Store large artifacts beside their source run or in separate artifact storage;
the revision/path/hash locates the evidence without copying raw transcripts here.
Never ingest credentials. The initial format has no public-export mode.
