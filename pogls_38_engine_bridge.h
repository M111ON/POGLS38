#ifndef POGLS_38_ENGINE_BRIDGE_H
#define POGLS_38_ENGINE_BRIDGE_H

#include <stdint.h>

typedef struct {
    uint32_t lane;
    uint32_t sig;
    uint8_t ok;
    uint8_t _pad[3];
} L38BridgeResult;

typedef struct {
    uint64_t total_writes;
} L38EngineBridge;

static inline L38BridgeResult l38_bridge_write(L38EngineBridge *b, uint64_t addr, uint64_t value, uint8_t world) {
    (void)addr;
    (void)value;
    L38BridgeResult r = {0};
    if (b) b->total_writes++;
    r.ok = 1;
    r.lane = (uint32_t)(addr % 54u);
    r.sig = (uint32_t)((addr ^ value ^ world) & 0xFFFFFFFFu);
    return r;
}

#endif
