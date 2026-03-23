# POGLS V3.6 — Complete Project Files
**Positional Geometry Logic Storage**  
Po · Ratchaburi · March 2026

## Core Law
```
A = floor(θ × 2²⁰)   PHI_UP=1,696,631   PHI_DOWN=648,055
```

## Directory Structure
```
core_c/       C headers + sources (V3.6 new + stable deps)
python/       Python layer (fabric, ingest, delta bridge, memory fabric)
benchmark/    Full benchmark suites (V3.5 + V3.6, Colab single-cell)
gui/          Tkinter GUI
legacy/       Deprecated WAL files (reference only)
docs/         Project reports (V3.4, V3.5, V3.6)
```

## Quick Start — AI Memory Fabric
```bash
python3 python/pogls_memory_fabric.py
# POST /remember  GET /recall  running on :7474
```

## Quick Start — Benchmark (Colab/Kaggle)
Upload `benchmark/pogls_hydra_colab.py` → run single cell

## Quick Start — Local Project Dashboard
```bash
python3 python/pogls_dashboard_local.py
# open http://127.0.0.1:8787
# manifest: python/pogls_dashboard_manifest.yaml
# optional extra repo: --repo POGLS4=/workspace/POGLS4
# export from UI: JSON / Markdown buttons
```

## Status
- All phases PASS on 5 platforms (Colab CPU/T4, Kaggle CPU/T4/P100)
- Kaggle P100: 1,031B audit ops in 60s (>1 Trillion) ✅
- fail=0 across all runs ✅
