# POGLS Repository

**Positional Geometry Logic Storage (POGLS)**

This repository now uses a modular root layout with three primary components:

```text
.
├── pogls_core/    # Shared core + storage primitives
├── POGLS4/        # V4x pipeline + tests
└── POGLS38/       # GPU throughput pipeline + tests
```

## Root Layout (Current)

### `pogls_core/` — shared core + storage
- `core_c/`
  - `pogls_delta.c`
  - `pogls_delta.h`
  - `pogls_delta_world_b.c`
  - `pogls_delta_world_b.h`
- `storage/`
  - `pogls_delta.h`
  - `pogls_shadow_delta_wired.h`
  - `pogls_spectre.h`
  - `pogls_spectre_delta_bridge.h`

### `POGLS4/` — V4x pipeline + tests
- Core headers:
  - `pogls_multi_anchor.h`
  - `pogls_pipeline_wire.h`
  - `pogls_qrpn.h`
  - `pogls_temporal_core.h`
  - `pogls_v4_snapshot.h`
  - `pogls_v4x_fed_bridge.h`
  - `pogls_v4x_wire.h`
- `tests/`
  - `test_bridge_compile.c`
  - `test_federation.c`
  - `test_v4x_full.c`
  - `test_v4x_stress.c`

### `POGLS38/` — GPU throughput + tests
- Core headers:
  - `pogls38_fed_bridge.h`
  - `pogls38_giant_shadow.h`
  - `pogls38_hydra_thin.h`
- `tests/`
  - `test_38_batch_feed.c`
  - `test_38_feedback.c`
  - `test_38_giant_shadow.c`
  - `test_38_hydra_thin.c`
  - `test_38_mesh_offset.c`

## Notes
- Historical/legacy flat files may still exist at repository root for archival continuity.
- Active modular development should target `pogls_core/`, `POGLS4/`, and `POGLS38/`.
