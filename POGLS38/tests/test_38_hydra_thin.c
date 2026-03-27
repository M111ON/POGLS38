/*
 * test_38_hydra_thin.c — unit tests for pogls38_hydra_thin.h v2
 *
 * T01  init — heads=2, threshold=256, magic correct
 * T02  which_head — lane→slice routing hard boundary
 * T03  ghost lane — (lane+27)%54, cross-slice guaranteed
 * T04  detach push — audit fail → ring only, no fed_write
 * T05  detach terminal — batch: pass→routed, fail→detached only
 * T06  detach ring overflow — drop_oldest, never blocks
 * T07  batch feed — pass=routed, fail=detached counts
 * T08  autoscale spawn — op_count > threshold*heads → spawn
 * T09  autoscale cap — never exceeds max 3
 * T10  slice lane boundary — 0-17/18-35/36-53
 * T11  batch_count increments per call
 * T12  detach flush — ring drains, returns count
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <inttypes.h>
#include <stdatomic.h>

/* ── Lightweight FederationCtx stub (must be BEFORE hydra_thin.h) ── */
#define POGLS_FEDERATION_H   /* suppress forward-decl in hydra_thin.h */

/* need lane constant before hydra_thin.h defines it */
#ifndef DETACH_DELTA_LANE
#  define DETACH_DELTA_LANE  53u
#endif

typedef struct {
    uint64_t op_count;
} FederationCtx;

static uint32_t fed_write_calls   = 0;  /* all fed_write calls           */
static uint32_t fed_write_normal  = 0;  /* iso=0 (main flow)             */
static uint32_t fed_write_quarantine = 0; /* iso=1 (detach, lane 53)     */

static inline void fed_write(FederationCtx *fed,
                             uint32_t packed, uint64_t lane, uint64_t value)
{
    (void)lane; (void)value;
    fed_write_calls++;
    /* iso bit [26] distinguishes quarantine writes from normal writes */
    if ((packed >> 26u) & 1u) fed_write_quarantine++;
    else                      fed_write_normal++;
    fed->op_count++;
}

/* reset all write counters between tests */
static inline void _reset_fed_counters(void) {
    fed_write_calls = fed_write_normal = fed_write_quarantine = 0;
}

/* ── real EngineSlice (header) ────────────────────────────────────── */
#include "pogls_engine_slice.h"

/* ── Subject under test ───────────────────────────────────────────── */
#include "pogls38_hydra_thin.h"

/* ══════════════════════════════════════════════════════════════════ */
static int pass_count = 0;
static int fail_count = 0;

#define CHECK(cond, name) do { \
    if (cond) { printf("  ✅ %s\n", name); pass_count++; } \
    else       { printf("  ❌ %s  (line %d)\n", name, __LINE__); fail_count++; } \
} while(0)

/* ── T01 ─────────────────────────────────────────────────────────── */
static void t01_init(void) {
    printf("\nT01 — init\n");
    L38HydraThin h;
    l38_hydra_thin_init(&h, 256);
    CHECK(h.magic        == HYDRA_THIN_MAGIC,   "magic correct");
    CHECK(h.heads_active == L38_THIN_MIN_HEADS, "heads_active=2");
    CHECK(h.threshold    == 256u,               "threshold=256");
    CHECK(h.heads[0].active == 1u,              "head[0] active");
    CHECK(h.heads[1].active == 1u,              "head[1] active");
    CHECK(h.heads[2].active == 0u,              "head[2] inactive");
    CHECK(h.total_routed   == 0u,               "routed=0");
    CHECK(h.total_detached == 0u,               "detached=0");
}

/* ── T02 ─────────────────────────────────────────────────────────── */
static void t02_which_head(void) {
    printf("\nT02 — which_head lane routing\n");
    CHECK(l38_which_head(0)  == 0u, "lane 0  → head 0");
    CHECK(l38_which_head(17) == 0u, "lane 17 → head 0");
    CHECK(l38_which_head(18) == 1u, "lane 18 → head 1");
    CHECK(l38_which_head(35) == 1u, "lane 35 → head 1");
    CHECK(l38_which_head(36) == 2u, "lane 36 → head 2");
    CHECK(l38_which_head(53) == 2u, "lane 53 → head 2");
}

/* ── T03 ─────────────────────────────────────────────────────────── */
static void t03_ghost_lane(void) {
    printf("\nT03 — ghost lane K3 cross-slice\n");
    int all_cross = 1;
    for (uint8_t lane = 0; lane < 54; lane++) {
        uint8_t ghost = l38_ghost_lane(lane);
        if (l38_which_head(lane) == l38_which_head(ghost)) {
            all_cross = 0; break;
        }
    }
    CHECK(all_cross,                      "every ghost crosses slice");
    CHECK(l38_ghost_lane(0)  == 27u,      "ghost(0)=27");
    CHECK(l38_ghost_lane(27) == 0u,       "ghost(27)=0");
    CHECK(l38_ghost_lane(53) == 26u,      "ghost(53)=26");
}

/* ── T04 ─────────────────────────────────────────────────────────── */
static void t04_detach_push_no_fed(void) {
    printf("\nT04 — detach push: ring only, no fed_write\n");
    L38HydraThin h;
    l38_hydra_thin_init(&h, 256);
    _reset_fed_counters();

    l38_hydra_detach_push(&h, 5, 0xAB, 0x1234, 0xDEAD, 1);

    CHECK(h.total_detached == 1u,          "total_detached=1");
    CHECK(h.heads[0].ops_detached == 1u,   "head[0].ops_detached=1");
    CHECK(h.heads[0].analytics.detach_count == 1u, "analytics updated");
    CHECK(fed_write_calls == 0u,            "NO fed_write on detach_push alone");
}

/* ── T05 ─────────────────────────────────────────────────────────── */
static void t05_detach_terminal(void) {
    printf("\nT05 — detach is terminal (pass→lane N, fail→lane 53 only)\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    l38_hydra_thin_init(&h, 256);
    _reset_fed_counters();

    uint32_t hil[4]   = {10, 20, 30, 40};
    uint8_t  lane[4]  = {0,  5,  10, 15};
    uint8_t  audit[4] = {0,  1,  0,  2};  /* idx 1,3 fail */

    l38_hydra_batch_feed(&h, &fed, hil, lane, audit, 4, 1);

    CHECK(h.total_detached        == 2u, "2 items detached");
    CHECK(h.total_routed          == 2u, "2 items routed");
    CHECK(fed_write_normal        == 2u, "2 fed_write iso=0 (main flow)");
    CHECK(fed_write_quarantine    == 2u, "2 fed_write iso=1 (quarantine lane 53)");
    /* KEY invariant: detach never re-enters main flow */
    CHECK(fed_write_normal        == h.total_routed,    "routed == normal writes");
    CHECK(fed_write_quarantine    == h.total_detached,  "detached == iso-1 writes");
}

/* ── T06 ─────────────────────────────────────────────────────────── */
static void t06_overflow(void) {
    printf("\nT06 — ring overflow drop_oldest\n");
    L38HydraThin h;
    l38_hydra_thin_init(&h, 256);

    for (uint32_t i = 0; i < DETACH_RING_SIZE + 100; i++)
        l38_hydra_detach_push(&h, 0, 1, i, i, 0);

    uint64_t ov = atomic_load(&h.detach.overflow);
    CHECK(ov >= 100u,                        "overflow counter ≥ 100");
    CHECK(h.total_detached == DETACH_RING_SIZE + 100, "all counted");
}

/* ── T07 ─────────────────────────────────────────────────────────── */
static void t07_batch_routing(void) {
    printf("\nT07 — batch routing counts\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    l38_hydra_thin_init(&h, 256);
    _reset_fed_counters();

    /* 6 items: pass=4, fail=2 */
    uint32_t hil[6]   = {1, 2, 3, 4, 5, 6};
    uint8_t  lane[6]  = {0, 17, 18, 35, 36, 53};
    uint8_t  audit[6] = {0,  1,  0,  1,  0,  0};

    l38_hydra_batch_feed(&h, &fed, hil, lane, audit, 6, 1);

    CHECK(h.total_routed          == 4u, "4 routed");
    CHECK(h.total_detached        == 2u, "2 detached");
    CHECK(fed_write_normal        == 4u, "4 iso=0 writes (main flow)");
    CHECK(fed_write_quarantine    == 2u, "2 iso=1 writes (quarantine)");
    CHECK(h.batch_count           == 1u, "batch_count=1");
}

/* ── T08 ─────────────────────────────────────────────────────────── */
static void t08_autoscale_spawn(void) {
    printf("\nT08 — autoscale: spawn when op_count > threshold*heads\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    l38_hydra_thin_init(&h, 256);

    CHECK(h.heads_active == 2u, "start=2");
    fed.op_count = 513;   /* > 256*2=512 */
    l38_hydra_autoscale(&h, &fed);

    CHECK(h.heads_active     == 3u, "spawned → 3");
    CHECK(h.heads[2].active  == 1u, "head[2] active");
    CHECK(h.spawn_count      == 1u, "spawn_count=1");
}

/* ── T09 ─────────────────────────────────────────────────────────── */
static void t09_autoscale_cap(void) {
    printf("\nT09 — autoscale cap at max 3\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    l38_hydra_thin_init(&h, 256);
    fed.op_count = 99999;

    l38_hydra_autoscale(&h, &fed);   /* 2→3 */
    l38_hydra_autoscale(&h, &fed);   /* capped */
    l38_hydra_autoscale(&h, &fed);   /* capped */

    CHECK(h.heads_active == L38_THIN_MAX_HEADS, "capped at 3");
    CHECK(h.spawn_count  == 1u,                 "only 1 spawn");
}

/* ── T10 ─────────────────────────────────────────────────────────── */
static void t10_slice_boundary(void) {
    printf("\nT10 — slice lane boundaries\n");
    L38HydraThin h;
    l38_hydra_thin_init(&h, 256);

    CHECK(h.heads[0].slice.lane_start ==  0u, "slice0 start=0");
    CHECK(h.heads[0].slice.lane_count == 18u, "slice0 count=18");
    CHECK(h.heads[1].slice.lane_start == 18u, "slice1 start=18");
    CHECK(h.heads[1].slice.lane_count == 18u, "slice1 count=18");
    CHECK(h.heads[2].slice.lane_start == 36u, "slice2 start=36");
    CHECK(h.heads[2].slice.lane_count == 18u, "slice2 count=18");
}

/* ── T11 ─────────────────────────────────────────────────────────── */
static void t11_batch_count(void) {
    printf("\nT11 — batch_count increments\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    l38_hydra_thin_init(&h, 256);
    uint32_t hil[1] = {1}; uint8_t lane[1] = {0}; uint8_t audit[1] = {0};

    for (int i = 0; i < 5; i++)
        l38_hydra_batch_feed(&h, &fed, hil, lane, audit, 1, (uint64_t)i);

    CHECK(h.batch_count == 5u, "batch_count=5");
}

/* ── T12 ─────────────────────────────────────────────────────────── */
static void t12_detach_flush(void) {
    printf("\nT12 — detach flush drains ring\n");
    L38HydraThin h;
    FederationCtx fed = {0};
    l38_hydra_thin_init(&h, 256);

    for (int i = 0; i < 10; i++)
        l38_hydra_detach_push(&h, (uint8_t)(i%54), 1, (uint32_t)i, (uint64_t)i, 0);

    uint32_t wpos = h.detach.write_pos;
    uint32_t flushed = l38_hydra_detach_flush(&h, &fed);

    CHECK(flushed == 10u,           "flushed=10");
    CHECK(h.detach.read_pos == wpos, "read_pos caught up");
}

/* ══════════════════════════════════════════════════════════════════ */
int main(void) {
    printf("═══════════════════════════════════════════════\n");
    printf("  test_38_hydra_thin — pogls38_hydra_thin.h v2\n");
    printf("═══════════════════════════════════════════════\n");

    t01_init();
    t02_which_head();
    t03_ghost_lane();
    t04_detach_push_no_fed();
    t05_detach_terminal();
    t06_overflow();
    t07_batch_routing();
    t08_autoscale_spawn();
    t09_autoscale_cap();
    t10_slice_boundary();
    t11_batch_count();
    t12_detach_flush();

    printf("\n═══════════════════════════════════════════════\n");
    printf("  RESULT: %d/%d pass\n", pass_count, pass_count + fail_count);
    if (fail_count == 0) printf("  ✅ ALL PASS\n");
    else                 printf("  ❌ %d FAILED\n", fail_count);
    printf("═══════════════════════════════════════════════\n");

    return fail_count == 0 ? 0 : 1;
}
