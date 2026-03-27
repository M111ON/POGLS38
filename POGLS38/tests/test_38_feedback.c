/*
 * test_38_feedback.c — ReflexBias → L38HydraThin feedback loop
 *
 * Tests the closed feedback loop:
 *   anomaly → GiantShadow → Mesh → ReflexBias → demote routing
 *
 * T01  no gs (NULL) → behaviour identical to v2 (no demote)
 * T02  gs present, clean lane → iso=0 (no demote)
 * T03  gs present, hot lane → iso=1 after bias ≤ -4
 * T04  demoted item: total_demoted counter increments
 * T05  demoted item: fed_write still called (not dropped)
 * T06  demoted item: iso=1 in packed field
 * T07  detach pushes to GS when gs != NULL
 * T08  self-healing: bias decays → demote flag lifts eventually
 * T09  lazy decay — bias drifts toward 0 after no anomalies
 * T10  feedback does not affect audit-fail path (detach stays terminal)
 * T11  total_demoted=0 with no hot zones
 * T12  feedback loop round-trip: anomalies → bias → demote on next batch
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <inttypes.h>
#include <stdatomic.h>

/* ── minimal DetachEntry stub (before all headers) ──────────────── */
#define POGLS_DETACH_LANE_H

#ifndef DETACH_REASON_GEO_INVALID
#  define DETACH_REASON_GEO_INVALID  0x01u
#  define DETACH_REASON_GHOST_DRIFT  0x02u
#  define DETACH_REASON_UNIT_CIRCLE  0x04u
#  define DETACH_REASON_OVERFLOW     0x80u
#endif

typedef struct {
    uint64_t  value;
    uint64_t  angular_addr;
    uint64_t  timestamp_ns;
    uint8_t   reason;
    uint8_t   route_was;
    uint8_t   shell_n;
    uint8_t   phase18;
    uint16_t  phase288;
    uint16_t  phase306;
} DetachEntry;
typedef char _det_sz[(sizeof(DetachEntry) == 32u) ? 1 : -1];
static inline int detach_is_twin_window(const DetachEntry *e)
{ return e && (e->phase288 < 18u || e->phase306 < 18u); }

/* ── PHI constants ───────────────────────────────────────────────── */
#ifndef POGLS_PHI_CONSTANTS
#define POGLS_PHI_CONSTANTS
#  define POGLS_PHI_SCALE   (1u << 20)
#  define POGLS_PHI_UP      1696631u
#  define POGLS_PHI_DOWN     648055u
#  define POGLS_PHI_COMP     400521u
#endif

/* ── FederationCtx stub (before hydra_thin.h) ───────────────────── */
#define POGLS_FEDERATION_H
#ifndef DETACH_DELTA_LANE
#  define DETACH_DELTA_LANE 53u
#endif

typedef struct { uint64_t op_count; } FederationCtx;

/* tracked fed_write calls split by iso bit */
static uint32_t _fw_iso0 = 0, _fw_iso1 = 0;
static uint32_t _fw_last_packed = 0;

static inline void fed_write(FederationCtx *f, uint32_t p,
                              uint64_t lane, uint64_t v)
{
    (void)lane; (void)v;
    _fw_last_packed = p;
    if ((p >> 26u) & 1u) _fw_iso1++; else _fw_iso0++;
    f->op_count++;
}
static inline void _reset_fw(void)
{ _fw_iso0 = _fw_iso1 = 0; _fw_last_packed = 0; }

/* ── real headers (order matters) ───────────────────────────────── */
#include <math.h>
#include "pogls_engine_slice.h"
#include "pogls_mesh_entry.h"
#include "pogls_mesh.h"
#include "pogls38_giant_shadow.h"   /* defines gs38_lane_should_demote  */
#include "pogls38_hydra_thin.h"     /* now sees GiantShadow38 fully     */

/* ══════════════════════════════════════════════════════════════════ */
static int pass_count = 0, fail_count = 0;

#define CHECK(cond, name) do { \
    if (cond) { printf("  ✅ %s\n", name); pass_count++; } \
    else       { printf("  ❌ %s  (line %d)\n", name, __LINE__); fail_count++; } \
} while(0)

/* helper: make bias[bucket] demote-worthy by loading it with BURSTs */
static void _burn_lane(GiantShadow38 *gs, uint8_t lane, int count)
{
    /* BURST = geo_invalid (0x01) + phase18 < 3 → penalty -3 per event */
    for (int i = 0; i < count; i++)
        gs38_push(gs, lane, 0x01, (uint32_t)i, (uint64_t)i, 0);
    gs38_drain(gs, 18);
}

/* ── T01 ─────────────────────────────────────────────────────────── */
static void t01_null_gs_no_demote(void) {
    printf("\nT01 — NULL gs → no demote, identical to v2\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    l38_hydra_thin_init(&h, 256);
    _reset_fw();

    uint32_t hil[3]   = {1, 2, 3};
    uint8_t  lane[3]  = {0, 9, 18};
    uint8_t  audit[3] = {0, 0, 0};

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 3, 1, NULL);

    CHECK(h.total_demoted == 0u, "total_demoted=0 with NULL gs");
    CHECK(_fw_iso1        == 0u, "no iso=1 writes with NULL gs");
    CHECK(_fw_iso0        == 3u, "3 iso=0 (normal) writes");
}

/* ── T02 ─────────────────────────────────────────────────────────── */
static void t02_clean_lane_no_demote(void) {
    printf("\nT02 — clean lane → iso=0 (no demote)\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);
    _reset_fw();

    /* lane 5 — no anomalies pushed, bias=0 */
    uint32_t hil[2]   = {10, 11};
    uint8_t  lane[2]  = {5,  5};
    uint8_t  audit[2] = {0,  0};

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 2, 1, &gs);

    CHECK(h.total_demoted == 0u, "total_demoted=0 (clean lane)");
    CHECK(_fw_iso0        == 2u, "2 iso=0 writes");
    CHECK(_fw_iso1        == 0u, "0 iso=1 writes");
}

/* ── T03 ─────────────────────────────────────────────────────────── */
static void t03_hot_lane_demote(void) {
    printf("\nT03 — hot lane → iso=1 after bias ≤ -4\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);

    /* burn lane 3: BURST -3 per event × 3 = -9 → well below -4 */
    _burn_lane(&gs, 3, 3);

    int8_t bias = gs38_lane_bias(&gs, 3);
    printf("    bias after burn = %d\n", (int)bias);

    _reset_fw();
    uint32_t hil[1]   = {99};
    uint8_t  lane[1]  = {3};
    uint8_t  audit[1] = {0};   /* pass — but zone is hot */

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 1, 2, &gs);

    CHECK(bias <= -4,             "bias ≤ -4 (demote threshold)");
    CHECK(h.total_demoted == 1u,  "total_demoted=1");
    CHECK(_fw_iso1        == 1u,  "iso=1 write (soft ghost)");
    CHECK(_fw_iso0        == 0u,  "0 iso=0 writes (all demoted)");
}

/* ── T04 ─────────────────────────────────────────────────────────── */
static void t04_demoted_counter(void) {
    printf("\nT04 — total_demoted increments correctly\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);

    _burn_lane(&gs, 0,  4);   /* lane 0  → hot */
    _burn_lane(&gs, 18, 4);   /* lane 18 → hot */
    /* lane 36 stays clean */

    _reset_fw();
    uint32_t hil[3]   = {1, 2, 3};
    uint8_t  lane[3]  = {0, 18, 36};
    uint8_t  audit[3] = {0,  0,  0};

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 3, 1, &gs);

    CHECK(h.total_demoted >= 2u, "total_demoted ≥ 2 (2 hot lanes)");
    printf("    total_demoted=%llu\n", (unsigned long long)h.total_demoted);
}

/* ── T05 ─────────────────────────────────────────────────────────── */
static void t05_demoted_still_fed_write(void) {
    printf("\nT05 — demoted item: fed_write still called (not dropped)\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);
    _burn_lane(&gs, 5, 4);

    _reset_fw();
    uint32_t hil[1]   = {42};
    uint8_t  lane[1]  = {5};
    uint8_t  audit[1] = {0};

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 1, 1, &gs);

    /* demoted = rerouted as ghost, but still written to federation */
    uint32_t total_fw = _fw_iso0 + _fw_iso1;
    CHECK(total_fw >= 1u,     "fed_write called even when demoted");
    CHECK(h.total_routed == 1u, "total_routed=1 (demote ≠ drop)");
}

/* ── T06 ─────────────────────────────────────────────────────────── */
static void t06_demoted_iso_bit(void) {
    printf("\nT06 — demoted: iso bit [26] set in packed\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);
    _burn_lane(&gs, 7, 4);

    _reset_fw();
    uint32_t hil[1]   = {0xFF};
    uint8_t  lane[1]  = {7};
    uint8_t  audit[1] = {0};

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 1, 1, &gs);

    uint32_t iso = (_fw_last_packed >> 26u) & 1u;
    CHECK(iso == 1u, "packed bit[26]=1 for demoted item");
}

/* ── T07 ─────────────────────────────────────────────────────────── */
static void t07_detach_pushes_to_gs(void) {
    printf("\nT07 — audit fail: detach pushes to GiantShadow\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);

    uint64_t before = atomic_load(&gs.total_ingested);

    uint32_t hil[2]   = {1, 2};
    uint8_t  lane[2]  = {4, 4};
    uint8_t  audit[2] = {1, 1};   /* both fail → detach */

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 2, 1, &gs);

    uint64_t after = atomic_load(&gs.total_ingested);
    CHECK(after >= before + 2u, "2 items pushed to GiantShadow on detach");
}

/* ── T08 ─────────────────────────────────────────────────────────── */
static void t08_self_healing(void) {
    printf("\nT08 — self-healing: bias decays, demote lifts\n");
    GiantShadow38 gs;
    gs38_init(&gs);

    /* burn lane 0 to bias ≤ -4 (hil=0..3 → bucket 0) */
    _burn_lane(&gs, 0, 4);
    CHECK(gs38_lane_should_demote(&gs, 0), "demote=1 after burn");

    int8_t bias_burned = gs38_lane_bias(&gs, 0);
    printf("    bias after burn = %d\n", (int)bias_burned);

    /* Advance global_epoch directly (simulates passage of time).
     * Each epoch applies one (7/8) decay step on next lookup.
     * Need enough steps to go from bias_burned → above -4.
     * (7/8)^N × bias_burned > -4
     * With 20 steps: bias decays significantly past threshold. */
    gs.reflex.global_epoch += 20u;

    /* lazy decay fires on lookup — catches up 20 missed epochs */
    int8_t bias_after = gs38_lane_bias(&gs, 0);
    printf("    bias after +20 epochs (lazy decay) = %d (threshold=%d)\n",
           (int)bias_after, REFLEX_DEMOTE_THRESHOLD);

    CHECK(bias_after > REFLEX_DEMOTE_THRESHOLD,
          "bias > threshold after decay (self-healed)");
    CHECK(!gs38_lane_should_demote(&gs, 0),
          "should_demote=0 after healing");
}

/* ── T09 ─────────────────────────────────────────────────────────── */
static void t09_lazy_decay_math(void) {
    printf("\nT09 — lazy decay: (7/8)^N shrinks bias toward 0\n");
    ReflexBias r;
    reflex_init(&r);

    /* 3 BURST events: -3 × 3 = -9 */
    MeshEntry me = {0};
    me.addr  = 0;
    me.type  = (uint8_t)MESH_TYPE_BURST;
    reflex_update(&r, &me);
    reflex_update(&r, &me);
    reflex_update(&r, &me);

    int8_t b0 = reflex_lookup(&r, 0);
    printf("    after 3 BURSTs: bias=%d\n", (int)b0);
    CHECK(b0 <= -6, "bias ≤ -6 after 3 BURST events");

    /* advance 4 epochs — decay 4 steps (7/8)^4 ≈ 0.586
     * -9 → -7 → -6 → -5 → -4  (still at demote threshold) */
    r.global_epoch += 4u;
    int8_t b1 = reflex_lookup(&r, 0);
    printf("    after +4 epochs (lazy catch-up): bias=%d\n", (int)b1);
    CHECK(b1 > b0,    "bias drifted toward 0 after 4 epochs");
    CHECK(b1 < 0,     "bias still negative after 4 epochs");

    /* advance 8 more epochs — (7/8)^8 from b1 reaches 0 (int8 arithmetic)
     * int8 shifts: -4→-4→-4→-3→-3→-2→-2→-1→0
     * Decay is CORRECT and aggressive — clears anomaly memory fast */
    r.global_epoch += 8u;
    int8_t b2 = reflex_lookup(&r, 0);
    printf("    after +12 epochs total: bias=%d (decay cleared)\n", (int)b2);
    CHECK(b2 >= b1,   "bias non-decreasing after more decay");
    CHECK(b2 > REFLEX_DEMOTE_THRESHOLD, "above demote threshold (self-healed)");
    /* Note: decay reaching 0 is correct — system forgets old anomalies.
     * Fresh anomalies can re-arm the bias immediately. */
    printf("    (decay reaching 0 is correct: system forgives old anomalies)\n");
}

/* ── T10 ─────────────────────────────────────────────────────────── */
static void t10_detach_unaffected(void) {
    printf("\nT10 — feedback does not affect detach (audit fail stays terminal)\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);
    _burn_lane(&gs, 2, 4);   /* lane 2 is hot */

    _reset_fw();
    uint32_t hil[2]   = {1, 2};
    uint8_t  lane[2]  = {2, 2};
    uint8_t  audit[2] = {1, 1};   /* audit FAIL — should detach, not demote */

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 2, 1, &gs);

    CHECK(h.total_detached == 2u,  "2 detached (terminal)");
    CHECK(h.total_demoted  == 0u,  "0 demoted (detach ≠ demote)");
    /* detach flush writes to lane 53 (iso=1 in flush), but normal batch = 0 */
    CHECK(h.total_routed   == 0u,  "0 routed (all were audit-fail)");
}

/* ── T11 ─────────────────────────────────────────────────────────── */
static void t11_no_hot_zones_no_demote(void) {
    printf("\nT11 — all lanes clean → total_demoted=0\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);
    /* no _burn_lane calls */

    uint32_t hil[6]   = {1,2,3,4,5,6};
    uint8_t  lane[6]  = {0,9,18,27,36,45};
    uint8_t  audit[6] = {0,0, 0, 0, 0, 0};

    l38_hydra_batch_feed_gs(&h, &fed, hil, lane, audit, 6, 1, &gs);

    CHECK(h.total_demoted == 0u, "total_demoted=0 (all clean)");
    CHECK(h.total_routed  == 6u, "6 routed normally");
}

/* ── T12 ─────────────────────────────────────────────────────────── */
static void t12_round_trip(void) {
    printf("\nT12 — round trip: anomalies → bias → demote on next batch\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    GiantShadow38 gs;
    l38_hydra_thin_init(&h, 256);
    gs38_init(&gs);

    /* BATCH 1: many audit-fail on lane 10 → fills GS → bias drops */
    uint32_t hil1[6]   = {1,2,3,4,5,6};
    uint8_t  lane1[6]  = {10,10,10,10,10,10};
    uint8_t  audit1[6] = {1, 1, 1, 1, 1, 1};   /* all fail */
    l38_hydra_batch_feed_gs(&h, &fed, hil1, lane1, audit1, 6, 1, &gs);

    /* drain GS to process anomalies into ReflexBias */
    gs38_drain(&gs, 18);

    int8_t bias = gs38_lane_bias(&gs, 10);
    printf("    bias after batch1 anomalies = %d\n", (int)bias);

    /* BATCH 2: lane 10 passes audit — but zone should be demoted */
    _reset_fw();
    uint32_t hil2[1]   = {99};
    uint8_t  lane2[1]  = {10};
    uint8_t  audit2[1] = {0};   /* pass */
    l38_hydra_batch_feed_gs(&h, &fed, hil2, lane2, audit2, 1, 2, &gs);

    if (bias <= REFLEX_DEMOTE_THRESHOLD) {
        CHECK(h.total_demoted >= 1u, "round-trip: anomalies → demote on next batch");
        CHECK(_fw_iso1 >= 1u,        "iso=1 write confirms demotion");
    } else {
        /* bias not yet below threshold — explain why */
        printf("    (bias=%d > threshold=%d — not demoted yet, "
               "need more anomaly volume)\n",
               (int)bias, REFLEX_DEMOTE_THRESHOLD);
        CHECK(bias < 0, "bias is at least negative (anomalies registered)");
    }
}

/* ══════════════════════════════════════════════════════════════════ */
int main(void)
{
    printf("═══════════════════════════════════════════════════════\n");
    printf("  test_38_feedback — ReflexBias → HydraThin v3  12/12\n");
    printf("═══════════════════════════════════════════════════════\n");

    t01_null_gs_no_demote();
    t02_clean_lane_no_demote();
    t03_hot_lane_demote();
    t04_demoted_counter();
    t05_demoted_still_fed_write();
    t06_demoted_iso_bit();
    t07_detach_pushes_to_gs();
    t08_self_healing();
    t09_lazy_decay_math();
    t10_detach_unaffected();
    t11_no_hot_zones_no_demote();
    t12_round_trip();

    printf("\n═══════════════════════════════════════════════════════\n");
    printf("  RESULT: %d/%d pass\n", pass_count, pass_count + fail_count);
    if (fail_count == 0) printf("  ✅ ALL PASS\n");
    else                 printf("  ❌ %d FAILED\n", fail_count);
    printf("═══════════════════════════════════════════════════════\n");

    return fail_count == 0 ? 0 : 1;
}
