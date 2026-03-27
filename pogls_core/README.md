# pogls_core

Shared, durable core module for POGLS families.

## Purpose
- Keep shared C core and federation bridge in one stable module.
- Minimize merge/update drift by exposing a single canonical location.

## Layout
- `core_c/` : canonical low-level C core implementation.
- `pogls_federation.h` : shared federation bridge contract.
