#ifndef POGLS_WIN32_COMPAT_H
#define POGLS_WIN32_COMPAT_H

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <io.h>

#ifndef fdatasync
#define fdatasync _commit
#endif

#ifndef usleep
#define usleep(x) Sleep((DWORD)(((x) + 999u) / 1000u))
#endif

#endif /* _WIN32 */

#endif /* POGLS_WIN32_COMPAT_H */
