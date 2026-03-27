/*
 * pogls38_hydra_thin.h — POGLS38 GPU Hydra Thin Layer  (v2 — rewrite)
 * ══════════════════════════════════════════════════════════════════════
 *
 * Concept (LOCKED — do not invert):
 *
 *   Hydra   = load balancer + safety valve
 *             DynamicHydra: heads_min=2, heads_max=3
 *             spawn/kill heads based on op_count (throughput-driven)
 *             NOT a worker-loop, NOT a retry engine
 *
 *   Slice   = EngineSlice descriptor (stateless, 24B)
 *             3 slices from 54 lanes: [0-17] [18-35] [36-53]
 *             assigned 1:1 to Hydra heads (head 0→slice 0 … head 2→slice 2)
 *             ghost cross-slice: (lane+27)%54 → K3 complete graph
 *             spawned by throughput load, NOT by anomaly queue
 *
 *   Detach  = terminal quarantine (shock absorber, NOT retry)
 *             fail → ring[4096] → async flush → delta lane 53 → END
 *             optional: aggregate summary → low-priority analytics
 *             ❌ no retry loop   ❌ no re-entry to main flow
 *
 *   Mesh    = Giant Shadow (phase N+1 — NOT in this file)
 *
 * Slice auto-scale rule (FROZEN):
 *   if (fed->op_count > HYDRA_THIN_THRESHOLD * heads_active)
 *       spawn_head()   →  activate next EngineSlice
 *   HYDRA_THIN_THRESHOLD = 256  (tunable at init)
 *   max heads = 3  (= SLICE_COUNT = 54/18)
 *
 * Detach flow:
 *   GPU batch audit fail
 *     → l38_hydra_detach_push()   ← hot path, no mutex
 *     → ring[4096]                ← drop_oldest if full
 *     → _hydra_detach_flush()     ← async, 500µs
 *     → delta lane 53             ← isolated, terminal
 *     [optional] analytics_summary accumulates per slice
 *
 * Integration:
 *   l38_hydra_batch_feed(hydra, fed, h_hil, h_lane, h_audit, N)
 *     → route each item to owning slice head
 *     → audit fail → detach_push (not fed_write)
 *     → after batch: autoscale check
 *
 * Constants (FROZEN):
 *   L38_THIN_LANES_PER_SLICE = 18   (54/3)
 *   L38_THIN_MAX_HEADS       = 3    (SLICE_COUNT)
 *   L38_THIN_MIN_HEADS       = 2    (duo core)
 *   HYDRA_THIN_THRESHOLD     = 256  (default, tunable)
 *   DETACH_DELTA_LANE        = 53   (inherited from detach_lane.h)
 *
 * ══════════════════════════════════════════════════════════════════════
 */
#ifndef POGLS38_HYDRA_THIN_H
#define POGLS38_HYDRA_THIN_H

#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <inttypes.h>
#include <stdatomic.h>

#include "pogls_engine_slice.h"

/*
 * FederationCtx — forward declaration only.
 * Caller must include pogls_federation.h (or provide a compatible
 * lightweight stub) BEFORE including this header.
 * Minimum required from caller:
 *   typedef struct { uint64_t op_count; ... } FederationCtx;
 *   void/GateResult fed_write(FederationCtx*, uint32_t, uint64_t, uint64_t);
 */
#ifndef POGLS_FEDERATION_H
typedef struct FederationCtx_s FederationCtx;
#endif

/* ══════════════════════════════════════════════════════════════════
 * Constants (FROZEN)
 * ══════════════════════════════════════════════════════════════════ */
#define L38_THIN_LANES_PER_SLICE   18u   /* 54/3 — FROZEN             */
#define L38_THIN_MAX_HEADS          3u   /* = SLICE_COUNT — FROZEN     */
#define L38_THIN_MIN_HEADS          2u   /* duo core — FROZEN          */
#define HYDRA_THIN_THRESHOLD_DEF  256u   /* ops/head before spawn      */

/* Detach ring (inherited geometry — DO NOT redefine if detach_lane.h
 * is also included; guard is here for standalone compilation only)   */
#ifndef DETACH_RING_SIZE
#  define DETACH_RING_SIZE   4096u
#  define DETACH_RING_MASK   (DETACH_RING_SIZE - 1u)
#  define DETACH_DELTA_LANE    53u
#  define DETACH_FLUSH_US     500u
#  define DETACH_FLUSH_BATCH   64u
#endif

#define HYDRA_THIN_MAGIC  0x48595448u   /* "HYTH" */

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  DATA TYPES  ─────────────────────────────
 * ══════════════════════════════════════════════════════════════════ */

/* ── DetachEntry — quarantine record (32B) ───────────────────────── */
typedef struct {
    uint64_t  value;        /* raw value that failed audit              */
    uint32_t  hil;          /* HIL address from GPU                     */
    uint8_t   lane;         /* lane [0..53]                             */
    uint8_t   audit;        /* original audit code from GPU             */
    uint8_t   slice_id;     /* owning slice [0,1,2]                     */
    uint8_t   _pad;
    uint64_t  seq;          /* monotonic sequence within this ring      */
    uint64_t  batch_id;     /* which GPU batch this came from           */
} L38DetachEntry;           /* 32B                                      */

typedef char _det_sz[(sizeof(L38DetachEntry) == 32u) ? 1 : -1];

/* ── Detach ring — SPSC, drop_oldest on overflow ─────────────────── */
typedef struct {
    L38DetachEntry  ring[DETACH_RING_SIZE];
    volatile uint32_t  write_pos;   /* producer (GPU batch thread)      */
    volatile uint32_t  read_pos;    /* consumer (flush thread)          */
    atomic_uint_fast64_t overflow;  /* drop_oldest counter              */
    atomic_uint_fast64_t seq_gen;   /* monotonic sequence               */
} L38DetachRing;

/* ── Per-slice analytics summary (optional, low-priority) ────────── */
typedef struct {
    uint64_t  detach_count;     /* total quarantined in this slice      */
    uint64_t  last_batch_id;    /* last batch that had a detach         */
    uint32_t  audit_histogram[8]; /* audit codes 0-7                   */
} L38SliceAnalytics;

/* ── Hydra head — wraps one EngineSlice + counters ───────────────── */
typedef struct {
    EngineSlice   slice;          /* descriptor (no state) — 24B        */
    uint64_t      ops_routed;     /* ops successfully routed to fed     */
    uint64_t      ops_detached;   /* ops quarantined by this head       */
    uint8_t       active;         /* 1 = running, 0 = idle              */
    uint8_t       _pad[7];
    L38SliceAnalytics analytics;  /* low-priority summary               */
} L38HydraHead;

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  MAIN STRUCT  ────────────────────────────
 *
 *  L38HydraThin
 *  ┌────────────────────────────────────────────────────────────┐
 *  │  heads[0]  │  heads[1]  │  heads[2]  │  (max 3)           │
 *  │  slice 0   │  slice 1   │  slice 2   │                    │
 *  │  lane 0-17 │  lane18-35 │  lane36-53 │                    │
 *  ├────────────────────────────────────────────────────────────┤
 *  │  detach_ring  → drain → delta lane 53  (terminal)          │
 *  ├────────────────────────────────────────────────────────────┤
 *  │  autoscale: op_count > threshold*heads → spawn head        │
 *  └────────────────────────────────────────────────────────────┘
 * ══════════════════════════════════════════════════════════════════ */
typedef struct L38HydraThin_s {
    uint32_t        magic;
    uint8_t         heads_active;   /* current [MIN..MAX]              */
    uint8_t         _pad[3];
    uint32_t        threshold;      /* ops/head before spawn           */

    L38HydraHead    heads[L38_THIN_MAX_HEADS];
    L38DetachRing   detach;         /* shared across all heads         */

    /* stats */
    uint64_t        total_routed;
    uint64_t        total_detached;
    uint64_t        total_demoted;   /* pass items soft-rerouted by ReflexBias */
    uint64_t        spawn_count;
    uint64_t        batch_count;
} L38HydraThin;   /* struct tag: L38HydraThin_s (matches forward decl) */

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  INIT  ───────────────────────────────────
 * ══════════════════════════════════════════════════════════════════ */
static inline void l38_hydra_thin_init(L38HydraThin *h, uint32_t threshold)
{
    if (!h) return;
    memset(h, 0, sizeof(*h));
    h->magic        = HYDRA_THIN_MAGIC;
    h->threshold    = (threshold > 0u) ? threshold : HYDRA_THIN_THRESHOLD_DEF;
    h->heads_active = L38_THIN_MIN_HEADS;   /* start with 2 heads (duo core) */

    /* init all 3 slice descriptors upfront; only heads_active are "on" */
    for (uint8_t i = 0u; i < L38_THIN_MAX_HEADS; i++) {
        slice_init(&h->heads[i].slice, i);
        h->heads[i].active = (i < L38_THIN_MIN_HEADS) ? 1u : 0u;
    }

    atomic_init(&h->detach.overflow, 0);
    atomic_init(&h->detach.seq_gen,  0);
}

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  SLICE ROUTING  ──────────────────────────
 *
 *  which_head(lane) — hard lane boundary
 *    lane 0-17  → head 0  (slice 0)
 *    lane 18-35 → head 1  (slice 1)
 *    lane 36-53 → head 2  (slice 2)
 *
 *  ghost cross-slice rule (FROZEN):
 *    ghost_lane = (lane + 27) % 54
 *    ghost always lands in a DIFFERENT slice → K3 complete graph
 * ══════════════════════════════════════════════════════════════════ */
static inline uint8_t l38_which_head(uint8_t lane)
{
    return (uint8_t)(lane / L38_THIN_LANES_PER_SLICE);   /* 0, 1, or 2 */
}

static inline uint8_t l38_ghost_lane(uint8_t lane)
{
    return (uint8_t)((lane + 27u) % 54u);   /* FROZEN — never modify */
}

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  DETACH (TERMINAL) ───────────────────────
 *
 *  Hot path — called from batch loop on audit fail.
 *  No mutex. SPSC drop_oldest semantics.
 *
 *  Detach is TERMINAL:
 *    ✅ ring → flush → delta lane 53
 *    ✅ analytics summary accumulates (low priority, non-blocking)
 *    ❌ no retry
 *    ❌ no re-entry to main flow
 * ══════════════════════════════════════════════════════════════════ */
static inline void l38_hydra_detach_push(
        L38HydraThin *h,
        uint8_t       lane,
        uint8_t       audit,
        uint32_t      hil,
        uint64_t      value,
        uint64_t      batch_id)
{
    L38DetachRing *dr = &h->detach;
    uint8_t head_idx  = l38_which_head(lane);
    uint64_t seq      = atomic_fetch_add_explicit(
                            &dr->seq_gen, 1u, memory_order_relaxed);

    uint32_t wpos     = dr->write_pos & DETACH_RING_MASK;
    uint32_t next     = (dr->write_pos + 1u) & DETACH_RING_MASK;

    /* drop_oldest: overwrite if full (never block) */
    if (next == (dr->read_pos & DETACH_RING_MASK)) {
        atomic_fetch_add_explicit(&dr->overflow, 1u, memory_order_relaxed);
        /* advance read_pos to make room (drop oldest) */
        dr->read_pos = (dr->read_pos + 1u) & DETACH_RING_MASK;
    }

    L38DetachEntry *e = &dr->ring[wpos];
    e->value    = value;
    e->hil      = hil;
    e->lane     = lane;
    e->audit    = audit;
    e->slice_id = head_idx;
    e->_pad     = 0;
    e->seq      = seq;
    e->batch_id = batch_id;

    /* memory fence before advancing write pointer */
    atomic_thread_fence(memory_order_release);
    dr->write_pos = (dr->write_pos + 1u) & DETACH_RING_MASK;

    /* update head counters (non-blocking) */
    if (head_idx < L38_THIN_MAX_HEADS) {
        h->heads[head_idx].ops_detached++;
        h->heads[head_idx].analytics.detach_count++;
        h->heads[head_idx].analytics.last_batch_id = batch_id;
        h->heads[head_idx].analytics.audit_histogram[audit & 0x7u]++;
    }
    h->total_detached++;
}

/* ── Flush ring → FederationCtx delta lane 53  (async-safe) ──────── *
 *  Call from a 500µs timer thread or end-of-batch cleanup.           *
 *  Returns number of entries flushed.                                *
 *  Terminal: entries are written to delta lane 53 and discarded.     */
static inline uint32_t l38_hydra_detach_flush(
        L38HydraThin  *h,
        FederationCtx *fed)          /* may be NULL (skip delta write) */
{
    L38DetachRing *dr = &h->detach;
    uint32_t flushed  = 0u;

    while (flushed < DETACH_FLUSH_BATCH) {
        uint32_t rpos = dr->read_pos & DETACH_RING_MASK;
        uint32_t wpos = dr->write_pos & DETACH_RING_MASK;
        if (rpos == wpos) break;   /* ring empty */

        atomic_thread_fence(memory_order_acquire);
        const L38DetachEntry *e = &dr->ring[rpos];

        /* write to isolated delta lane 53 (terminal quarantine) */
        if (fed) {
            /* packed: hil in low bits, lane in [25:20], iso=1 (detach) */
            uint32_t packed = (e->hil & 0xFFFFFu)
                            | ((uint32_t)(e->lane & 0x3Fu) << 20u)
                            | (1u << 26u);   /* iso = 1 for detach */
            fed_write(fed, packed, DETACH_DELTA_LANE, e->value);
            /* note: fed_commit is NOT called from here —
             * detach writes accumulate; commit happens on normal cycle */
        }

        dr->read_pos = (dr->read_pos + 1u) & DETACH_RING_MASK;
        flushed++;
    }
    return flushed;
}

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  AUTOSCALE  ──────────────────────────────
 *
 *  Rule (FROZEN):
 *    if (fed->op_count > threshold * heads_active) → spawn head
 *    if heads already at max (3) → no-op
 *    kill: not implemented (GPU = sustained load; heads stay alive)
 *
 *  Comparison map:
 *    BEFORE (wrong)  │  NOW (correct)
 *    ────────────────┼──────────────────────────────
 *    trigger=detach  │  trigger=fed->op_count
 *    retry loop      │  spawn head (new slice)
 *    external call   │  self-regulating (auto)
 * ══════════════════════════════════════════════════════════════════ */
static inline void l38_hydra_autoscale(L38HydraThin *h, FederationCtx *fed)
{
    if (!h || !fed) return;
    if (h->heads_active >= L38_THIN_MAX_HEADS) return;   /* already at max */

    /* throughput gate: spawn only when load justifies it */
    uint64_t load_gate = (uint64_t)h->threshold * h->heads_active;
    if (fed->op_count <= load_gate) return;

    /* activate next head */
    uint8_t next = h->heads_active;   /* 0-indexed: if active=2, next=2 */
    if (next >= L38_THIN_MAX_HEADS) return;

    h->heads[next].active = 1u;
    h->heads_active++;
    h->spawn_count++;

    /* (no thread launch here — thin layer is descriptor-only;
     *  caller (l38_fed_batch_feed) routes to active heads by slice) */
}

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  BATCH FEED (main entry) ─────────────────
 *
 *  l38_hydra_batch_feed()
 *
 *  For each item in GPU batch:
 *    1. derive lane from h_lane[i] % 54
 *    2. find owning head (l38_which_head)
 *    3. if head active AND audit pass → fed_write
 *    4. if audit fail → detach_push (terminal)
 *    5. ghost lane: (lane+27)%54 → cross-slice link (K3)
 *  After batch:
 *    → autoscale check
 *    → detach flush (inline, up to FLUSH_BATCH entries)
 *
 *  h_audit[i] == 0  → pass
 *  h_audit[i] != 0  → fail → detach (terminal quarantine)
 * ══════════════════════════════════════════════════════════════════ */
static inline void l38_hydra_batch_feed(
        L38HydraThin  *h,
        FederationCtx *fed,
        const uint32_t *h_hil,      /* GPU hil array   [N]             */
        const uint8_t  *h_lane,     /* GPU lane array  [N]             */
        const uint8_t  *h_audit,    /* GPU audit array [N] (0=pass)    */
        uint32_t        N,
        uint64_t        batch_id)
{
    if (!h || !fed || !h_hil || !h_lane || !h_audit || N == 0u) return;

    for (uint32_t i = 0u; i < N; i++) {
        uint8_t  lane    = (uint8_t)(h_lane[i] % 54u);
        uint8_t  head_id = l38_which_head(lane);
        uint32_t hil     = h_hil[i];
        uint8_t  audit   = h_audit[i];

        /* ── DETACH path (terminal) ─────────────────────────────── */
        if (audit != 0u) {
            l38_hydra_detach_push(h, lane, audit, hil, (uint64_t)hil, batch_id);
            continue;   /* ← hard stop, no fed_write, no retry */
        }

        /* ── MAIN path: route to owning slice head ──────────────── */
        if (head_id < h->heads_active && h->heads[head_id].active) {
            /*
             * packed cell layout (matches fed_gate):
             *   hil   = bit[19:0]
             *   lane  = bit[25:20]
             *   iso   = bit[26]   = 0 (valid)
             */
            uint32_t packed = (hil & 0xFFFFFu)
                            | ((uint32_t)(lane & 0x3Fu) << 20u);
            fed_write(fed, packed, (uint64_t)lane, (uint64_t)hil);

            h->heads[head_id].ops_routed++;
            h->total_routed++;
        } else {
            /*
             * Head not yet active (slice not spawned yet).
             * Route to head 0 as fallback (always active, slice 0).
             * Ghost will bridge cross-slice when mesh is added.
             */
            uint32_t packed = (hil & 0xFFFFFu)
                            | ((uint32_t)(lane & 0x3Fu) << 20u);
            fed_write(fed, packed, (uint64_t)lane, (uint64_t)hil);
            h->heads[0].ops_routed++;
            h->total_routed++;
        }

        /*
         * Ghost cross-slice annotation (K3 — no extra fed_write here).
         * Mesh/GiantShadow will consume this in phase N+1.
         * Formula is FROZEN: ghost = (lane+27)%54
         */
        (void)l38_ghost_lane(lane);   /* computed, reserved for mesh */
    }

    h->batch_count++;

    /* autoscale after batch (throughput-driven, self-regulating) */
    l38_hydra_autoscale(h, fed);

    /* inline detach flush (terminal drain) */
    l38_hydra_detach_flush(h, fed);
}

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  DIAGNOSTICS  ────────────────────────────
 * ══════════════════════════════════════════════════════════════════ */
static inline void l38_hydra_thin_print(const L38HydraThin *h)
{
    if (!h) return;
    printf("[L38HydraThin] magic=%08X  heads=%u/%u  threshold=%u\n",
           h->magic, h->heads_active, L38_THIN_MAX_HEADS, h->threshold);
    printf("  routed=%" PRIu64 "  detached=%" PRIu64
           "  spawns=%" PRIu64 "  batches=%" PRIu64 "\n",
           h->total_routed, h->total_detached,
           h->spawn_count,  h->batch_count);

    for (uint8_t i = 0u; i < L38_THIN_MAX_HEADS; i++) {
        const L38HydraHead *hd = &h->heads[i];
        printf("  head[%u] slice=%u lanes[%u-%u] active=%u "
               "routed=%" PRIu64 " detached=%" PRIu64 "\n",
               i,
               hd->slice.engine_id,
               hd->slice.lane_start,
               (uint8_t)(hd->slice.lane_start + hd->slice.lane_count - 1u),
               hd->active,
               hd->ops_routed,
               hd->ops_detached);
    }

    uint64_t overflow = atomic_load_explicit(
                            &((L38HydraThin*)h)->detach.overflow,
                            memory_order_relaxed);
    printf("  detach_ring  overflow=%" PRIu64 "\n", overflow);
}

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────── BATCH FEED v3 — WITH REFLEX FEEDBACK ───────────
 *
 *  l38_hydra_batch_feed_gs()
 *
 *  Same as l38_hydra_batch_feed() but adds ReflexBias feedback:
 *
 *  Decision tree per item:
 *
 *    audit fail → detach (terminal, unchanged)
 *
 *    audit pass →
 *      gs38_lane_should_demote(gs, lane)?
 *        YES → packed iso=1  (soft ghost — bias says zone is hot)
 *              fed_write with iso=1 → federation treats as ghost
 *              h->total_demoted++
 *        NO  → packed iso=0  (normal MAIN route)
 *
 *  GiantShadow38 is optional (NULL = no feedback, same as v2):
 *    l38_hydra_batch_feed_gs(h, fed, ..., NULL)  ← no feedback
 *    l38_hydra_batch_feed_gs(h, fed, ..., gs)    ← with feedback
 *
 *  Feedback loop (closed):
 *    GPU anomaly → detach → GiantShadow.push()
 *    GiantShadow.drain() → Mesh → reflex_update() → bias--
 *    Next batch → should_demote? → iso=1 (soft reroute)
 *    Federation sees iso=1 → routes as GHOST (not MAIN)
 *    → anomaly zone stops getting MAIN writes automatically
 *
 *  Comparison map:
 *    v2 (no feedback)    │  v3 (with ReflexBias)
 *    ────────────────────┼──────────────────────────────────────
 *    all pass → iso=0    │  pass + hot zone → iso=1 (demote)
 *    static routing      │  adaptive: learns from history
 *    no memory           │  bias[256], lazy decay, self-healing
 *
 * ══════════════════════════════════════════════════════════════════ */

/* forward decl — GiantShadow38 defined in pogls38_giant_shadow.h   */
#ifndef POGLS38_GIANT_SHADOW_H
struct GiantShadow38_s;
typedef struct GiantShadow38_s GiantShadow38;
/* stub for standalone compile — real impl in pogls38_giant_shadow.h */
static inline int  _gs38_demote_stub(void *gs, uint8_t lane)
    { (void)gs; (void)lane; return 0; }
static inline void _gs38_push_stub(void *gs, uint8_t lane, uint8_t audit,
                                   uint32_t hil, uint64_t value, uint64_t bid)
    { (void)gs;(void)lane;(void)audit;(void)hil;(void)value;(void)bid; }
#  define _GS38_SHOULD_DEMOTE(gs,lane)   _gs38_demote_stub(gs,lane)
#  define _GS38_PUSH(gs,l,a,h,v,b)      _gs38_push_stub(gs,l,a,h,v,b)
#else
#  define _GS38_SHOULD_DEMOTE(gs,lane)   gs38_lane_should_demote(gs,lane)
#  define _GS38_PUSH(gs,l,a,h,v,b)      gs38_push(gs,l,a,h,v,b)
#endif

static inline void l38_hydra_batch_feed_gs(
        L38HydraThin  *h,
        FederationCtx *fed,
        const uint32_t *h_hil,
        const uint8_t  *h_lane,
        const uint8_t  *h_audit,
        uint32_t        N,
        uint64_t        batch_id,
        void           *gs)          /* GiantShadow38* or NULL           */
{
    if (!h || !fed || !h_hil || !h_lane || !h_audit || N == 0u) return;

    for (uint32_t i = 0u; i < N; i++) {
        uint8_t  lane    = (uint8_t)(h_lane[i] % 54u);
        uint8_t  head_id = l38_which_head(lane);
        uint32_t hil     = h_hil[i];
        uint8_t  audit   = h_audit[i];

        /* ── DETACH path (terminal, unchanged from v2) ──────────── */
        if (audit != 0u) {
            l38_hydra_detach_push(h, lane, audit, hil, (uint64_t)hil, batch_id);
            /* also push to GiantShadow for async Mesh processing */
            if (gs) _GS38_PUSH(gs, lane, audit, hil, (uint64_t)hil, batch_id);
            continue;
        }

        /* ── REFLEX FEEDBACK: query bias before routing ─────────── */
        uint8_t iso = 0u;   /* default: normal MAIN route */
        if (gs && _GS38_SHOULD_DEMOTE(gs, lane)) {
            iso = 1u;       /* bias ≤ -4: soft ghost reroute          */
            h->total_demoted++;
        }

        /* ── MAIN / DEMOTED path ─────────────────────────────────── */
        uint8_t  route_head = (iso == 0u && head_id < h->heads_active
                               && h->heads[head_id].active)
                             ? head_id : 0u;

        uint32_t packed = (hil & 0xFFFFFu)
                        | ((uint32_t)(lane  & 0x3Fu) << 20u)
                        | ((uint32_t)(iso         )  << 26u);

        fed_write(fed, packed, (uint64_t)lane, (uint64_t)hil);
        h->heads[route_head].ops_routed++;
        h->total_routed++;

        (void)l38_ghost_lane(lane);   /* K3 ghost annotation — for mesh */
    }

    h->batch_count++;
    l38_hydra_autoscale(h, fed);
    l38_hydra_detach_flush(h, fed);
}

/* ══════════════════════════════════════════════════════════════════
 *  ─────────────────────  CONCEPT MAP  ────────────────────────────
 *
 *  WRONG (v1)            │  CORRECT (v2)
 *  ──────────────────────┼──────────────────────────────────────────
 *  retry loop            │  terminal quarantine (no retry)
 *  split on detach depth │  spawn on op_count > threshold*heads
 *  external trigger      │  self-regulating (throughput only)
 *  detach == retry       │  detach == shock absorber → analytics
 *  Hydra = worker loop   │  Hydra = load balancer + safety valve
 *
 *  MENTAL MODEL (LOCKED):
 *
 *    Hydra            DynamicHydra
 *    ┌────────────────────────────────────────────────┐
 *    │  head 0 (always on)  │  head 1 (always on)     │
 *    │  slice 0: lane 0-17  │  slice 1: lane 18-35    │
 *    │                      │                         │
 *    │  [head 2 spawns when op_count > 2*threshold]   │
 *    │  slice 2: lane 36-53                           │
 *    └────────────────────────────────────────────────┘
 *         │ audit fail → detach_push (no return)
 *         ▼
 *    ring[4096] → flush → delta lane 53 → TERMINAL
 *         │ optional low-priority
 *         ▼
 *    analytics_summary (audit_histogram per slice)
 *
 * ══════════════════════════════════════════════════════════════════ */

#endif /* POGLS38_HYDRA_THIN_H */
