#ifndef POGLS_WAL_MMAP_H
#define POGLS_WAL_MMAP_H

/*
 * Minimal WAL mmap compatibility layer.
 * Provides WALMmap + WSRecord API expected by core_c/*.
 */

#include <stdint.h>
#include <stddef.h>
#include <stdatomic.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t op;
    uint16_t lane;
    uint32_t frame_id;
    uint64_t addr;
    uint64_t value;
    uint32_t crc32;
    uint32_t _pad;
} WSRecord;

_Static_assert(sizeof(WSRecord) == 32, "WSRecord must be 32 bytes");

typedef struct {
    WSRecord       *base;
    uint32_t        capacity;
    _Atomic uint32_t write_pos;
    _Atomic uint32_t flush_seq;
} WALMmap;

static inline void wal_mmap_bind(WALMmap *wm, WSRecord *base, uint32_t capacity)
{
    if (!wm) return;
    wm->base = base;
    wm->capacity = capacity;
    atomic_store(&wm->write_pos, 0u);
    atomic_store(&wm->flush_seq, 0u);
}

static inline WSRecord *wal_alloc_record(WALMmap *wm)
{
    if (!wm || !wm->base || wm->capacity == 0u) return NULL;
    uint32_t idx = atomic_fetch_add_explicit(&wm->write_pos, 1u, memory_order_relaxed);
    if (idx >= wm->capacity) return NULL;
    return &wm->base[idx];
}

static inline void wm_signal_flush(WALMmap *wm)
{
    if (!wm) return;
    (void)atomic_fetch_add_explicit(&wm->flush_seq, 1u, memory_order_release);
}

#ifdef __cplusplus
}
#endif

#endif /* POGLS_WAL_MMAP_H */
