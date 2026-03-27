# POGLS Repository Structure

Updated: 2026-03-27

## Canonical Root Layout

```text
.
├── pogls_core/
│   ├── core_c/
│   │   ├── pogls_delta.c
│   │   ├── pogls_delta.h
│   │   ├── pogls_delta_world_b.c
│   │   └── pogls_delta_world_b.h
│   └── storage/
│       ├── pogls_delta.h
│       ├── pogls_shadow_delta_wired.h
│       ├── pogls_spectre.h
│       └── pogls_spectre_delta_bridge.h
│
├── POGLS4/
│   ├── pogls_multi_anchor.h
│   ├── pogls_pipeline_wire.h
│   ├── pogls_qrpn.h
│   ├── pogls_temporal_core.h
│   ├── pogls_v4_snapshot.h
│   ├── pogls_v4x_fed_bridge.h
│   ├── pogls_v4x_wire.h
│   └── tests/
│       ├── test_bridge_compile.c
│       ├── test_federation.c
│       ├── test_v4x_full.c
│       └── test_v4x_stress.c
│
└── POGLS38/
    ├── pogls38_fed_bridge.h
    ├── pogls38_giant_shadow.h
    ├── pogls38_hydra_thin.h
    └── tests/
        ├── test_38_batch_feed.c
        ├── test_38_feedback.c
        ├── test_38_giant_shadow.c
        ├── test_38_hydra_thin.c
        └── test_38_mesh_offset.c
```

## Placement Rules

- Shared core and storage primitives live in `pogls_core/`.
- V4x pipeline implementation and tests live in `POGLS4/`.
- GPU throughput implementation and tests live in `POGLS38/`.
- The structure above is the canonical modular layout for current work.

## Legacy Notes

- Additional top-level files/directories may remain for migration history and archived artifacts.
- Do not use legacy flat placement for new modular updates.
