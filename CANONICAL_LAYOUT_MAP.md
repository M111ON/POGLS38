# Canonical Layout + Active File Map

This repo now uses a canonical 3-domain layout to separate **active source-of-truth** from **legacy/archive** assets and reduce duplicate edits.

## Canonical Domains

- `pogls_core/` → shared core contracts and federation interfaces (authoritative).
- `POGLS4/` → V4 CPU pipeline domain (reserved; fill only with V4-active files).
- `POGLS38/` → V38/GPU throughput domain (authoritative for v38 bridges/tests).

## Active File Mapping (Source-of-Truth)

| Canonical path (active) | Previous path | Status |
|---|---|---|
| `pogls_core/pogls_federation.h` | `pogls_federation.h` | **source-of-truth** |
| `POGLS38/pogls38_fed_bridge.h` | `pogls38_fed_bridge.h` | **source-of-truth** |
| `POGLS38/pogls38_hydra_thin.h` | `pogls38_hydra_thin.h` | **source-of-truth** |
| `POGLS38/pogls38_giant_shadow.h` | `pogls38_giant_shadow.h` | **source-of-truth** |
| `POGLS38/tests/test_38_giant_shadow.c` | `test_38_giant_shadow.c` | **source-of-truth** |

## Legacy/Archive Mapping

| Path | Classification | Notes |
|---|---|---|
| Root shim files (`pogls_federation.h`, `pogls38_*.h`, `test_38_giant_shadow.c`) | legacy compatibility shim | Include-forward only; do not edit logic here. |
| `legacy/` | legacy/archive | Deprecated WAL/reference code. |
| `zip/`, `*.zip` | archive snapshot | Historical release artifacts only. |
| Duplicate dashboard trees (`pogls_dashboard/` vs `python/pogls_dashboard/`) | transitional duplicate | Prefer `python/pogls_dashboard/` for active Python integration unless explicitly maintaining root copy. |

## Editing Rules (Zero-Waste I/O)

1. Edit only canonical files in `pogls_core/`, `POGLS4/`, `POGLS38/`.
2. Keep root shims minimal include-forwarders for backward compatibility.
3. Treat `legacy/` and zip snapshots as read-only archive.
4. If a file must be promoted from legacy to active, move it into a canonical domain and update this map.

## Next cleanup (optional)

- Migrate `test/test_38_*.c` into `POGLS38/tests/` as canonical test entrypoints.
- Consolidate dashboard to a single active path to eliminate duplicate maintenance.
