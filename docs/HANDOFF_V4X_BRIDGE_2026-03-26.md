# POGLS V4x Federation Bridge — Handoff
Date: 2026-03-26

## Current status

```
test_v4x_full    31/31  ✅
test_v4x_stress  15/15  ✅  (S05 normalized /N)
test_federation  34/34  ✅
test_bridge      gate_passed=713 ghosted=7 dropped=0 epoch=1 ✅
```

## Remaining last item (feedback lane)

`test_38_feedback` is the final non-clean item observed in earlier runs:

```
RESULT: 22/29 pass
```

The failing expectation was tied to anomaly→bias progression timing in the
round-trip check where bias did not go negative quickly enough before the
assertion point. In practical terms, this is a sequencing/tuning issue
between:

- anomaly accumulation window,
- decay cadence, and
- demote threshold check timing.

Recommended close-out path:

1. lock deterministic seed/input ordering for that test,
2. validate bias after each mini-batch (not just end-of-step),
3. align threshold assertion with the same window used by demote logic,
4. rerun until score reaches `30/30`.

## S05 fix (root cause + correction)

Root cause:
- `anchor_changes` counted per-core updates (N cores)
- `anchor_enforces` counted per-event
- direct ratio `anchor_changes / anchor_enforces` was inflated by ~N

Fix:
- normalize by core count:

```c
rate = anchor_changes / (anchor_enforces * N);
```

Example from current run:
- `550 / (250 * 4) = 55%`
- falls in healthy target range `[5%, 80%]` and passes.

## Bridge notes

- Commit entry carries lane information used by federation packing.
- Packed layout still follows fed gate invariant:
  - `hil`  = bits `[19:0]`
  - `lane` = bits `[25:20]`
  - `iso`  = bit `[26]`
  - invariant: `hil % 54 == lane`
- warm-up / op_count sync should remain tied to V4x total steps.

## Frozen constants

- `FED_LANE_MODULO = 54`
- `TC_CYCLE = 720`
- paired write invariant (`X + nX`) stays enabled.
