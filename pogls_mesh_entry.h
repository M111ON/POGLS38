#ifndef POGLS_MESH_ENTRY_H
#define POGLS_MESH_ENTRY_H

#include <stdint.h>

#define DETACH_REASON_GEO_INVALID 1u
#define DETACH_REASON_GHOST_DRIFT 2u
#define DETACH_REASON_UNIT_CIRCLE 4u

typedef struct {
    uint64_t value;
    uint64_t angular_addr;
    uint8_t lane;
    uint8_t reason;
    uint16_t _pad;
} MeshEntry;

typedef struct {
    int16_t bucket[256];
} ReflexBias;

typedef struct {
    MeshEntry items[1024];
    uint16_t head;
    uint16_t tail;
    uint16_t count;
} MeshEntryBuf;

static inline void mesh_entry_buf_init(MeshEntryBuf *b) {
    if (!b) return;
    b->head = b->tail = b->count = 0;
}

#endif
