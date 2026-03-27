# POGLS Repo Structure — Post Session 2026-03-26
## Status: V4x ✅ | GPU Bridge ✅ | Hydra Thin v3 ✅ | GiantShadow ✅ | ReflexFeedback ✅

---

## Recommended Layout

```
pogls/
├── pogls_core/                    ← git submodule (shared ground truth)
│   ├── core_c/                    ← ห้ามแตะ
│   │   ├── pogls_delta.c
│   │   └── pogls_delta_world_b.c
│   ├── storage/
│   │   ├── pogls_delta.h
│   │   ├── pogls_shadow_delta_wired.h
│   │   ├── pogls_spectre.h
│   │   └── pogls_spectre_delta_bridge.h
│   ├── pogls_platform.h           ← PHI constants (FROZEN)
│   ├── pogls_federation.h         ← FederationCtx + fed_write + fed_commit
│   ├── pogls_engine_slice.h       ← EngineSlice descriptor (FROZEN)
│   ├── pogls_detach_lane.h        ← DetachEntry + detach_is_twin_window
│   ├── pogls_mesh_entry.h         ← MeshEntry + ReflexBias + mesh_translate
│   └── pogls_mesh.h               ← Mesh + Voronoi + Delaunay + Tail
│
├── POGLS4/                        ← V4x CPU pipeline
│   ├── pogls_v4x_wire.h           ← V4xCommitEntry (lane field added)
│   ├── pogls_v4x_fed_bridge.h     ← V4x → Federation bridge ✅ 31+15+34+713
│   ├── pogls_pipeline_wire.h
│   ├── pogls_temporal_core.h
│   ├── pogls_multi_anchor.h
│   ├── pogls_qrpn.h
│   ├── tests/
│   │   ├── test_v4x_full.c        ← 31/31 ✅
│   │   ├── test_v4x_stress.c      ← 15/15 ✅
│   │   ├── test_federation.c      ← 34/34 ✅
│   │   └── test_bridge_compile.c  ← gate_passed=713 ✅
│   └── BUILD.md
│
└── POGLS38/                       ← GPU throughput pipeline
    ├── pogls38_fed_bridge.h       ← GPU → Federation bridge ✅ 100/100
    ├── pogls38_hydra_thin.h       ← Hydra v3 + ReflexFeedback ✅ 50/50
    ├── pogls38_giant_shadow.h     ← GiantShadow38 + WorkSteal ✅ 47/47
    ├── tests/
    │   ├── test_38_bridge.c       ← 100/100 ✅
    │   ├── test_38_hydra_thin.c   ← 50/50  ✅
    │   ├── test_38_giant_shadow.c ← 47/47  ✅
    │   └── test_38_feedback.c     ← 30/30  ✅
    └── BUILD.md
```

---

## File Ownership Map

| File | Repo | Touches | Status |
|------|------|---------|--------|
| `core_c/pogls_delta.c` | pogls_core | ❌ FROZEN | shared |
| `core_c/pogls_delta_world_b.c` | pogls_core | ❌ FROZEN | shared |
| `pogls_platform.h` | pogls_core | ❌ FROZEN | shared |
| `pogls_federation.h` | pogls_core | ✅ paired write fix | v1.2 |
| `pogls_engine_slice.h` | pogls_core | ❌ FROZEN | shared |
| `pogls_detach_lane.h` | pogls_core | read-only | shared |
| `pogls_mesh_entry.h` | pogls_core | read-only | v1.1 |
| `pogls_mesh.h` | pogls_core | read-only | stable |
| `pogls_v4x_wire.h` | POGLS4 | lane field added | ✅ |
| `pogls_v4x_fed_bridge.h` | POGLS4 | NEW this session | ✅ |
| `pogls38_fed_bridge.h` | POGLS38 | NEW this session | ✅ |
| `pogls38_hydra_thin.h` | POGLS38 | NEW v3 this session | ✅ |
| `pogls38_giant_shadow.h` | POGLS38 | NEW this session | ✅ |

---

## Frozen Constants (NEVER move these)

```c
FED_LANE_MODULO          = 54
FED_GATE_PHI             = 0x9E3779B9
TC_CYCLE                 = 720
TC_ANCHOR                = 144
PHI_UP                   = 1696631
PHI_DOWN                 = 648055
L38_THIN_LANES_PER_SLICE = 18    // 54/3
L38_THIN_MAX_HEADS       = 3
GS_STEAL_OFFSET          = 27    // ghost cross-slice (FROZEN)
DETACH_DELTA_LANE        = 53    // isolated quarantine lane
Sacred numbers: 17, 18, 54, 144, 162, 289
paired write X+nX — เขียนคู่เสมอ
core_c/ — ห้ามแตะเด็ดขาด
```

---

## Build Commands

```bash
# POGLS4 bridge test
gcc -std=c11 -O2 -D_POSIX_C_SOURCE=200809L \
  pogls_core/core_c/pogls_delta.c \
  pogls_core/core_c/pogls_delta_world_b.c \
  POGLS4/tests/test_bridge_compile.c \
  -I pogls_core/ -I POGLS4/ \
  -o test_bridge

# POGLS38 hydra thin
gcc -std=c11 -O2 -D_POSIX_C_SOURCE=200809L \
  POGLS38/tests/test_38_hydra_thin.c \
  -I pogls_core/ -I POGLS38/ \
  -o test_38_hydra_thin

# POGLS38 giant shadow
gcc -std=c11 -O2 -D_POSIX_C_SOURCE=200809L \
  POGLS38/tests/test_38_giant_shadow.c \
  -I pogls_core/ -I POGLS38/ -lm \
  -o test_38_giant_shadow

# POGLS38 feedback loop
gcc -std=c11 -O2 -D_POSIX_C_SOURCE=200809L \
  POGLS38/tests/test_38_feedback.c \
  -I pogls_core/ -I POGLS38/ -lm \
  -o test_38_feedback
```

---

## Migration Script (bash)

```bash
#!/bin/bash
# migrate_to_submodule.sh
# Run from project root. Creates the recommended layout.

set -e

mkdir -p pogls_core/core_c pogls_core/storage
mkdir -p POGLS4/tests
mkdir -p POGLS38/tests

# pogls_core — shared ground truth
cp core_c/pogls_delta.c          pogls_core/core_c/
cp core_c/pogls_delta_world_b.c  pogls_core/core_c/
cp storage/pogls_delta.h         pogls_core/storage/
cp storage/pogls_shadow_delta_wired.h pogls_core/storage/
cp storage/pogls_spectre.h            pogls_core/storage/
cp storage/pogls_spectre_delta_bridge.h pogls_core/storage/
cp pogls_platform.h              pogls_core/
cp pogls_federation.h            pogls_core/
cp pogls_engine_slice.h          pogls_core/
cp pogls_detach_lane.h           pogls_core/
cp pogls_mesh_entry.h            pogls_core/
cp pogls_mesh.h                  pogls_core/

# POGLS4
cp pogls_v4x_wire.h              POGLS4/
cp pogls_v4x_fed_bridge.h        POGLS4/
cp pogls_pipeline_wire.h         POGLS4/
cp pogls_temporal_core.h         POGLS4/
cp pogls_multi_anchor.h          POGLS4/
cp pogls_qrpn.h                  POGLS4/
cp test_v4x_full.c               POGLS4/tests/
cp test_v4x_stress.c             POGLS4/tests/
cp test_federation.c             POGLS4/tests/
cp test_bridge_compile.c         POGLS4/tests/

# POGLS38
cp pogls38_fed_bridge.h          POGLS38/
cp pogls38_hydra_thin.h          POGLS38/
cp pogls38_giant_shadow.h        POGLS38/
cp test_38_bridge.c              POGLS38/tests/ 2>/dev/null || true
cp test_38_hydra_thin.c          POGLS38/tests/
cp test_38_giant_shadow.c        POGLS38/tests/
cp test_38_feedback.c            POGLS38/tests/

echo "Migration complete."
echo "Next: cd pogls_core && git init && git add . && git commit -m 'init shared core'"
echo "Then: cd .. && git submodule add ./pogls_core pogls_core"
```

---

## Git Submodule Init (after migration)

```bash
# 1. Init pogls_core as its own repo
cd pogls_core
git init
git add .
git commit -m "pogls_core: shared ground truth v1.2"
cd ..

# 2. Add as submodule in parent repos
# In POGLS4:
cd POGLS4
git init
git submodule add ../pogls_core pogls_core
git add .
git commit -m "POGLS4: V4x + Federation bridge"

# In POGLS38:
cd ../POGLS38
git init
git submodule add ../pogls_core pogls_core
git add .
git commit -m "POGLS38: Hydra v3 + GiantShadow + ReflexFeedback"
```

---

## Include Path Update (after migration)

```c
// BEFORE (flat layout):
#include "pogls_engine_slice.h"
#include "pogls_federation.h"

// AFTER (submodule layout):
#include "pogls_core/pogls_engine_slice.h"
#include "pogls_core/pogls_federation.h"

// OR with -I flag:
// gcc -I pogls_core/ ...
// then keep: #include "pogls_engine_slice.h"  ← no change needed
```

---

## Next Session Priorities

```
Priority 1: Wire gs38_addr_bias(hil) เข้า batch_feed_gs
            (ใช้ hil จริงจาก GPU แทน lane representative)
            → accuracy สูงขึ้น (per-address, not per-lane)

Priority 2: Mesh phase N+1 — Giant Shadow offset store
            mesh = Giant Shadow เก็บ offset ระหว่าง cores

Priority 3: Run migrate_to_submodule.sh จริง + verify builds
```
