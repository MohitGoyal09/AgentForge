# Forecast lineage example

This example shows that AgentForge records can link forecast revisions to the evidence cited and to the outcome. It uses Headline Arena (HA) style daily gold (GC) directional challenges: an agent submits bearish, neutral and bullish probabilities before a deadline and can revise.

## Everything here is synthetic

No network, no LLM calls, no HA API calls, no real GC price data. Timestamps are fixed, so the output is deterministic. Outcomes are made up. Source URLs point at ALFRED series pages (DGS10, DTWEXBGS) with the vintage date in its own field. Gold itself is not on FRED. The content hashes are of fixed synthetic strings, not real downloads.

## Files

- `build_example.py`: stdlib only. Writes the three files below and prints a summary. `python build_example.py --check` also runs the self-check.
- `events.jsonl`: one synthetic session in the AgentForge event envelope (`schema_version`, `session_id`, `turn`, `sequence`, `type`, `timestamp`, `payload`) as written by `PersistenceManager.append_event`. Sequence numbers rise strictly. Event types: `run_config`, `source_retrieved`, `forecast_submitted`, `challenge_resolved`, and the recovery events `agent_error`, `retry`, `compaction`, `checkpoint_restored`. `agent_error` is the string the harness already uses for errors.
- `versions.csv`: one row per submitted version. The `adjustment` column is empty on purpose. It is kept apart from `brier_unadjusted`. `cited_event_seqs` and `recovery_event_seqs` are `;` separated. `tool_calls_used` counts `source_retrieved`, `agent_error` and `retry` events per challenge: those after the previous `challenge_resolved` event (or session start) up to that submission. The budget is per challenge.
- `challenges.csv`: one row per challenge, with the synthetic outcome and the final version's Brier score.

## The story

- GC-A v1: initial. A newer DGS10 vintage is then retrieved and cited in v2 (`new`). After an error, retry, compaction and checkpoint restore, v3 cites only sources it already had (`recovery_only`).
- GC-B v1: initial, vector `reconstructed` from direction and confidence. v2 cites a source seen before v1, with no recovery events (`previously_seen`).

## Reconstruction rule

When only a direction and a confidence are known, the chosen direction gets `confidence` and the other two categories split the remainder evenly. Bullish at 0.6 gives bearish 0.2, neutral 0.2, bullish 0.6. Rows built this way have `vector_provenance = reconstructed`.

## Label rule

Each revision is compared with the previous submission of the same challenge.

- A cited source is new if its `publish_time` is later than the previous submission time AND its `sha256` appears in no event before the previous submission.
- Recovery events are `agent_error`, `retry`, `compaction` and `checkpoint_restored` with a sequence between the previous and the current submission.

| New cited source | Recovery events | Label |
|---|---|---|
| yes | yes | `mixed` |
| yes | no | `new` |
| no (only old sources) | yes | `recovery_only` |
| no (only old sources) | no | `previously_seen` |
| nothing cited | no | `unknown` |

The first version of a challenge is `initial`. If nothing is cited and there are recovery events, the label is `recovery_only`.

## Brier score (unadjusted)

`brier = sum over k in {bearish, neutral, bullish} of (p_k - o_k)^2`, where `o` is one-hot on the outcome. Range 0 to 2. Rounded to 4 decimals in the CSVs. Probabilities must sum to 1.

## Limits

- Citations are agent-reported. They show what the agent said it used, not causal proof that the evidence drove the revision.
- This tests record support, not forecast quality. The Brier scores come from two made-up outcomes.
- The receipts are synthetic stand-ins for HA submission receipts.
