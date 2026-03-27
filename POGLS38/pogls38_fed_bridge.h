/*
 * pogls38_fed_bridge.h — POGLS38 GPU → Federation Bridge
 * ══════════════════════════════════════════════════════════════════════
 *
 * Feeds GPU kernel SoA output directly into FederationCtx,
 * bypassing L38WirePipeline entirely.
 *
 * GPU kernel produces (SoA, N elements, host-side after cudaMemcpy):
 *   h_hil[N]   uint32_t — hilbert spatial address
 *   h_lane[N]  uint8_t  — h_hil % 54 (pre-computed on GPU)
 *   h_audit[N] uint8_t  — 0=pass (addr%17==1), 1=fail (iso)
 *
 * Packed cell layout (must match fed_gate):
 *   hil  = bit[19:0]   → h_hil[i] % 54 (= h_lane[i])
 *   lane = bit[25:20]  → h_lane[i]
 *   iso  = bit[26]     → h_audit[i]
 *   invariant: hil % 54 == lane ✓
 *
 * FROZEN constants (from GPU bench):
 *   L38_GPU_SV   = 34   step vector
 *   L38_GPU_BASE = 1    base addr
 */

#pragma once
#include <stdint.h>
#include <string.h>
#include "pogls_federation.h"

/* ── constants (FROZEN) ─────────────────────────────────────────── */
#define L38_FED_SV        34u               /* step vector — FROZEN from bench */
#define L38_FED_BASE       1u               /* base addr   — FROZEN            */
#define L38_FED_BATCH_MAX (2u * 1024u * 1024u)  /* 2M cells/batch              */

/* ── feed stats ─────────────────────────────────────────────────── */
typedef struct {
    uint64_t batches;       /* total l38_fed_batch_feed() calls  */
    uint64_t cells_total;   /* total cells processed             */
    uint64_t fed_pass;      /* cells that entered fed_write() → PASS */
    uint64_t fed_ghost;     /* cells ghosted (iso fail or warm-up)   */
    uint64_t fed_drop;      /* cells dropped by fed_gate             */
} L38FedStats;

/* ── packed cell builder ────────────────────────────────────────── */
/*
 * GPU provides h_lane[i] = h_hil[i] % 54 pre-computed.
 * hil = h_lane ensures hil%54 == lane invariant.
 */
static inline uint32_t l38_to_packed(uint8_t lane, uint8_t iso)
{
    uint32_t hil = (uint32_t)lane;          /* hil%54 == lane ✓ */
    return  (hil & 0xFFFFFu)                /* bit[19:0] = hil  */
          | ((uint32_t)(lane & 0x3Fu) << 20)/* bit[25:20] = lane*/
          | ((uint32_t)(iso  & 1u)   << 26);/* bit[26]    = iso */
}

/*
 * l38_fed_batch_feed — takes GPU kernel SoA output (host-side after
 * cudaMemcpy) and feeds each element through fed_write().
 * Returns: number of cells that reached GATE_PASS
 */
static inline uint32_t l38_fed_batch_feed(
        FederationCtx        *fed,
        const uint32_t       *h_hil,
        const uint8_t        *h_lane,
        const uint8_t        *h_audit,
        uint32_t              N,
        L38FedStats          *stats)
{
    if (!fed || !h_hil || !h_audit || !stats) return 0;
    if (N > L38_FED_BATCH_MAX) N = L38_FED_BATCH_MAX;

    uint32_t passed = 0;
    stats->batches++;
    stats->cells_total += N;

    for (uint32_t i = 0; i < N; i++) {
        uint8_t lane = h_lane ? h_lane[i] : (uint8_t)(h_hil[i] % 54u);
        uint8_t iso  = h_audit[i] & 1u;

        uint64_t angular_addr = (uint64_t)L38_FED_BASE
                              + (uint64_t)L38_FED_SV * (uint64_t)i;
        uint64_t value = ((uint64_t)h_hil[i] << 8) | (uint64_t)lane;
        uint32_t packed = l38_to_packed(lane, iso);

        GateResult gr = fed_write(fed, packed, angular_addr, value);
        if      (gr == GATE_PASS)  { stats->fed_pass++;  passed++; }
        else if (gr == GATE_GHOST) { stats->fed_ghost++;           }
        else                       { stats->fed_drop++;            }
    }
    return passed;
}

static inline void l38_fed_stats_print(const L38FedStats *s)
{
    if (!s) return;
    uint64_t t = s->cells_total ? s->cells_total : 1;
    printf("\n╔══════════════════════════════════════════════════╗\n");
    printf("║  POGLS38 GPU → Federation Feed Stats             ║\n");
    printf("╠══════════════════════════════════════════════════╣\n");
    printf("║  Batches:     %10llu                            ║\n", (unsigned long long)s->batches);
    printf("║  Total cells: %10llu                            ║\n", (unsigned long long)s->cells_total);
    printf("║  Pass:        %10llu (%3llu%%)                    ║\n",
           (unsigned long long)s->fed_pass,
           (unsigned long long)(s->fed_pass * 100u / t));
    printf("║  Ghost:       %10llu (%3llu%%)                    ║\n",
           (unsigned long long)s->fed_ghost,
           (unsigned long long)(s->fed_ghost * 100u / t));
    printf("║  Drop:        %10llu (%3llu%%)                    ║\n",
           (unsigned long long)s->fed_drop,
           (unsigned long long)(s->fed_drop * 100u / t));
    printf("╚══════════════════════════════════════════════════╝\n\n");
}
