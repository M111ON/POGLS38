#ifndef POGLS_PLATFORM_H
#define POGLS_PLATFORM_H

#include <stdint.h>

#define PHI_SCALE (1u << 20)
#define PHI_UP 1696631u
#define PHI_DOWN 648055u

#define POGLS_PHI_SCALE PHI_SCALE
#define POGLS_PHI_UP PHI_UP
#define POGLS_PHI_DOWN PHI_DOWN
#define POGLS_PHI_COMP (PHI_SCALE - 1u)

#define POGLS_GHOST_STREAK_MAX 8u

#endif
