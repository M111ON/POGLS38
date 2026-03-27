# POGLS Handoff — Session End
## Date: 2026-03-26
## Status: V4x Bridge ✅ | GPU Bridge ✅ | Hydra Thin ⚠️ needs rework

---

## TEST SCORES (confirmed this session)

```
test_v4x_full      31/31  ✅
test_v4x_stress    15/15  ✅  (S05 normalized /N)
test_federation    34/34  ✅
test_bridge        gate_passed=713  ghosted=7  dropped=0  epoch=1  ✅
test_38_bridge     pass=100  drop=0  audit=clean  ✅
```

---

## FILES CHANGED THIS SESSION

| File | Change |
|------|--------|
| `pogls_v4x_wire.h` | `V4xCommitEntry._pad` → `lane` (= `v_clean%54`) |
| `pogls_federation.h` | `delta_append_v3` → `storage_delta_ab_append` (paired write) + `_pad` → `commit_pending` |
| `pogls_v4x_fed_bridge.h` | NEW — V4x→Federation bridge |
| `pogls38_fed_bridge.h` | NEW — GPU→Federation bridge (direct) |
| `pogls38_hydra_thin.h` | NEW — แต่ concept ผิด ต้องเขียนใหม่ (ดูด้านล่าง) |
| `test_v4x_stress.c` | S05 rate normalized by N |
| `POGLS_SYSTEM_DOC.md` | NEW — Architecture + API reference |

---

## HYDRA THIN — ต้องเขียนใหม่ ⚠️

### Mental model ที่ถูก (confirmed ก่อน session จบ)

```
Hydra    = duo core — 2 heads ทำงานคู่กัน
Slice    = งอก core ใหม่ bounded ≤ original size
           มีความสามารถเหมือน core เดิมทุกอย่าง
           trigger จาก load ของ core (ไม่ใช่ anomaly queue)
Detach   = quarantine จริงๆ — ไม่ใช่ retry loop
Mesh     = Giant Shadow เก็บ offset ระหว่าง cores (phase ถัดไป)
```

### สิ่งที่ผิดใน version ปัจจุบัน

```
❌ L38DetachQueue มี retry loop — detach = quarantine จริง ไม่ retry
❌ split trigger จาก detach depth — ควร trigger จาก core load
❌ concept detach ≠ quarantine+retry
```

### คำถามที่ยังไม่ได้ answer (ถามใน session ถัดไป)

```
1. Slice งอก trigger จากอะไร?
   → throughput threshold (op_count > X)?
   → explicit call จากภายนอก?

2. Detach — cell quarantine แล้วหายไปเลย
   หรือมี mechanism อื่นดึงกลับ (ไม่ใช่ retry)?
```

---

## ARCHITECTURE (current frozen)

```
V4x (CPU, time-driven)          GPU (throughput-driven)
  v4x_fed_step()                  l38_hydra_batch_feed()  ← thin hydra (TODO)
       ↓                          l38_fed_batch_feed()    ← direct (working)
       └──────────┬───────────────┘
                  ▼
           FederationCtx  (pogls_core/)
                  ↓
         12-step commit → paired disk write → shadow record
```

### Repo layout (recommended)

```
pogls_core/          ← submodule (shared ground truth)
  core_c/
  storage/
  pogls_federation.h

POGLS4/
  pogls_v4x_wire.h
  pogls_v4x_fed_bridge.h

POGLS38/
  pogls38_fed_bridge.h
  pogls38_hydra_thin.h  ← ต้องเขียนใหม่
```

---

## FROZEN CONSTANTS (ห้ามแตะ)

```c
FED_LANE_MODULO   = 54
FED_GATE_PHI      = 0x9E3779B9
TC_CYCLE          = 720
TC_ANCHOR         = 144
PHI_UP            = 1696631
PHI_DOWN          = 648055
L38_THIN_LANES_PER_SLICE = 18   // 54/3
L38_THIN_MAX_ACTIVE      = 2    // split-world phase
Sacred: 17, 18, 54, 144, 162, 289
paired write X+nX — ต้องเขียนคู่เสมอ
core_c/ — ห้ามแตะ
```

---

## NEXT SESSION

```
Priority 1: เขียน pogls38_hydra_thin.h ใหม่
  - Hydra = duo core (2 heads)
  - Slice = งอก core ใหม่ trigger จาก load
  - Detach = quarantine จริง (ไม่ retry)
  - ถาม: slice trigger condition + detach fate

Priority 2: mesh = Giant Shadow (offset store)
  → phase ถัดไป ยังไม่ทำ

Priority 3: move files ไป repo จริง (pogls_core submodule)
```

---

## BUILD COMMAND (working)

```bash
gcc -std=c11 -O2 -D_POSIX_C_SOURCE=200809L \
  core_c/pogls_delta.c core_c/pogls_delta_world_b.c \
  test_bridge_compile.c -I. -o test_bridge
```
