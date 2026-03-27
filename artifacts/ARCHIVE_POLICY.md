# Archive Policy

## Purpose
Historical snapshot archives must be isolated from active source code to keep the working tree modular and reduce I/O noise.

## Rules
1. Store historical snapshot archives only under `artifacts/archive/` (or publish them as release assets).
2. Keep source-tree root and code folders free of versioned `.zip` snapshots.
3. Keep only explicitly required reference archives in the main source tree when absolutely necessary.
4. Document every retained reference archive in `artifacts/archive/manifest.md` with:
   - filename
   - retention reason
   - expected removal/review trigger

## Review cadence
Review retained references each release cycle and remove anything no longer required.
