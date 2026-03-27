/*
 * test_38_mesh_offset.c — GiantShadow38 Mesh N+1 offset store tests
 *
 * T01  init zero — gs_offset all zero, gs_offset_updates == 0
 * T02  first entry — no offset written (need 2 entries same cluster)
 * T03  second entry — offset written after 2nd ingest same cluster
 * T04  offset value — delta = addr2 - addr1
 * T05  negative offset — addr2 < addr1 → negative delta stored
 * T06  independent clusters — offset[c0] != offset[c1] independently
 * T07  gs38_get_offset accessor — returns correct value
 * T08  gs38_predict_next — base + offset
 * T09  null guard — gs38_get_offset(NULL, 0) == 0
 * T10  updates counter — increments per second-or-later entry per cluster
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>

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

typedef char _detach_entry_sz[(sizeof(DetachEntry) == 32u) ? 1 : -1];

static inline int detach_is_twin_window(const DetachEntry *e)
{
    return e && (e->phase288 < 18u || e->phase306 < 18u);
}

#ifndef POGLS_PHI_CONSTANTS
#define POGLS_PHI_CONSTANTS
#  define POGLS_PHI_SCALE   (1u << 20)
#  define POGLS_PHI_UP      1696631u
#  define POGLS_PHI_DOWN     648055u
#  define POGLS_PHI_COMP     400521u
#endif

#include "pogls_engine_slice.h"
#include "pogls_mesh_entry.h"
#include "pogls_mesh.h"
#include "pogls38_giant_shadow.h"

/* ══════════════════════════════════════════════════════════════════ */
static int pass_count = 0, fail_count = 0;
#define CHECK(cond, name) do { \
    if (cond) { printf("  ✅ %s\n", name); pass_count++; } \
    else       { printf("  ❌ %s  (line %d)\n", name, __LINE__); fail_count++; } \
} while(0)

/* ── helper: push one item directly to gs and drain it through Mesh ─ */
static void feed_and_drain(GiantShadow38 *gs, uint32_t hil,
                            uint64_t value, uint64_t batch_id)
{
    uint8_t lane = (uint8_t)(hil % 54u);
    gs38_push(gs, lane, 0u, hil, value, batch_id);
    gs38_drain(gs, 18u);
}

/* Determine which cluster a hil maps to (mirrors _gs38_process_one) */
static uint8_t hil_to_cluster(uint32_t hil)
{
    uint32_t mask = POGLS_PHI_SCALE - 1u;
    uint32_t addr = (uint32_t)(hil & mask);
    uint32_t a    = (uint32_t)(((uint64_t)addr * POGLS_PHI_UP)   >> 20) & mask;
    uint32_t b    = (uint32_t)(((uint64_t)addr * POGLS_PHI_DOWN) >> 20) & mask;
    return voronoi_classify(a, b);
}

/* Find two hil values that map to the same cluster */
static void find_same_cluster_pair(uint32_t *hil1, uint32_t *hil2)
{
    uint8_t target = hil_to_cluster(0u);
    *hil1 = 0u;
    *hil2 = 0u;
    for (uint32_t h = 1u; h < 1000u; h++) {
        if (hil_to_cluster(h) == target) {
            *hil2 = h;
            return;
        }
    }
}

/* ══════════════════════════════════════════════════════════════════ */
int main(void)
{
    printf("=== test_38_mesh_offset ===\n\n");

    /* T01 — init zero */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);
        int all_zero = 1;
        for (int i = 0; i < MESH_MAX_CLUSTERS; i++)
            if (gs->gs_offset[i] != 0) { all_zero = 0; break; }
        CHECK(all_zero, "T01 gs_offset all zero after init");
        CHECK(gs->gs_offset_updates == 0, "T01 gs_offset_updates == 0");
        free(gs);
    }

    /* T02 — first entry: no offset written */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);
        feed_and_drain(gs, 0u, 0xAAu, 1u);
        uint8_t c = hil_to_cluster(0u);
        CHECK(gs->gs_offset[c] == 0, "T02 first entry: offset stays 0");
        CHECK(gs->gs_offset_updates == 0, "T02 first entry: updates still 0");
        free(gs);
    }

    /* T03 + T04 — second entry same cluster: offset written */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);

        uint32_t h1, h2;
        find_same_cluster_pair(&h1, &h2);
        uint8_t c = hil_to_cluster(h1);

        feed_and_drain(gs, h1, 0x10u, 10u);
        feed_and_drain(gs, h2, 0x20u, 11u);

        int64_t expected = (int64_t)h2 - (int64_t)h1;
        CHECK(gs->gs_offset_updates >= 1u, "T03 updates >= 1 after 2nd entry");
        CHECK(gs->gs_offset[c] == expected, "T04 offset == addr2 - addr1");
        free(gs);
    }

    /* T05 — negative offset */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);

        uint32_t h1, h2;
        find_same_cluster_pair(&h1, &h2);
        /* feed in reverse order → negative delta */
        uint8_t c = hil_to_cluster(h1);

        feed_and_drain(gs, h2, 0x10u, 20u);
        feed_and_drain(gs, h1, 0x20u, 21u);

        int64_t expected = (int64_t)h1 - (int64_t)h2;
        CHECK(expected < 0, "T05 setup: expected < 0");
        CHECK(gs->gs_offset[c] == expected, "T05 negative offset stored correctly");
        free(gs);
    }

    /* T06 — independent clusters
     * PHI scatter: cluster 0 owns low hil values (0..~128k).
     * Use pre-computed hil anchors from cluster analysis.            */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);

        /* cluster 0: h1=0, h2=1 */
        uint32_t h1=0u, h2=1u;
        uint8_t c0 = hil_to_cluster(h1);

        /* cluster 7: first hil = 128851, second = 128851+54 (same lane offset) */
        uint32_t hx=128851u;
        /* find a second hil in cluster 7 */
        uint32_t hy=0u;
        uint8_t cx = hil_to_cluster(hx);
        for (uint32_t h=hx+1u; h<hx+200u; h++) {
            if (hil_to_cluster(h)==cx) { hy=h; break; }
        }

        /* sanity */
        CHECK(c0 != cx, "T06 clusters are distinct");

        feed_and_drain(gs, h1, 1u, 30u);
        feed_and_drain(gs, h2, 2u, 31u);
        feed_and_drain(gs, hx, 3u, 32u);
        if (hy) feed_and_drain(gs, hy, 4u, 33u);

        int64_t off0 = gs38_get_offset(gs, c0);
        int64_t exp0 = (int64_t)h2 - (int64_t)h1;
        CHECK(off0 == exp0, "T06 cluster 0 offset correct");

        free(gs);
    }

    /* T07 — gs38_get_offset accessor */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);
        uint32_t h1, h2;
        find_same_cluster_pair(&h1, &h2);
        uint8_t c = hil_to_cluster(h1);
        feed_and_drain(gs, h1, 1u, 40u);
        feed_and_drain(gs, h2, 2u, 41u);
        int64_t via_accessor = gs38_get_offset(gs, c);
        int64_t expected     = (int64_t)h2 - (int64_t)h1;
        CHECK(via_accessor == expected, "T07 gs38_get_offset matches direct");
        free(gs);
    }

    /* T08 — gs38_predict_next */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);
        uint32_t h1, h2;
        find_same_cluster_pair(&h1, &h2);
        uint8_t c = hil_to_cluster(h1);
        feed_and_drain(gs, h1, 1u, 50u);
        feed_and_drain(gs, h2, 2u, 51u);
        uint64_t predicted = gs38_predict_next(gs, (uint64_t)h2, c);
        uint64_t expected  = (uint64_t)((int64_t)h2 + ((int64_t)h2 - (int64_t)h1));
        CHECK(predicted == expected, "T08 gs38_predict_next == base + offset");
        free(gs);
    }

    /* T09 — null guard */
    {
        int64_t v = gs38_get_offset(NULL, 0u);
        CHECK(v == 0, "T09 null gs returns 0");
        uint64_t p = gs38_predict_next(NULL, 100u, 0u);
        CHECK(p == 100u, "T09 predict_next null → base unchanged");
    }

    /* T10 — updates counter */
    {
        GiantShadow38 *gs = calloc(1, sizeof(GiantShadow38));
        gs38_init(gs);
        uint32_t h1, h2;
        find_same_cluster_pair(&h1, &h2);
        feed_and_drain(gs, h1, 1u, 60u);
        feed_and_drain(gs, h2, 2u, 61u);
        feed_and_drain(gs, h1, 3u, 62u);  /* 3rd → 2nd update */
        CHECK(gs->gs_offset_updates >= 2u, "T10 updates >= 2 after 3 entries same cluster");
        free(gs);
    }

    printf("\n=== %d/%d passed", pass_count, pass_count + fail_count);
    if (fail_count == 0) printf(" ✅ ALL PASS");
    printf(" ===\n");
    return fail_count ? 1 : 0;
}
