#ifndef POGLS_38_ENGINE_H
#define POGLS_38_ENGINE_H

#include <stdint.h>

typedef struct {
    uint8_t merkle_root[8];
    uint8_t algo_id;
    uint8_t migration;
    uint8_t slice_id;
    uint8_t slice_flags;
    uint8_t reserved[4];
} HoneycombSlot;

typedef struct {
    uint8_t payload[48];
    HoneycombSlot honeycomb;
} DiamondBlock;

typedef struct {
    uint8_t active_count;
} L38SpawnCtrl;

#endif
