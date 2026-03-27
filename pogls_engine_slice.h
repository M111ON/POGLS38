#ifndef POGLS_ENGINE_SLICE_H
#define POGLS_ENGINE_SLICE_H

#include <stdint.h>

#define SLICE_COUNT 3u
#define SLICE_LANE_WIDTH 18u

static inline uint8_t slice_of_lane(uint8_t lane) {
    return (uint8_t)(lane / SLICE_LANE_WIDTH);
}

#endif
