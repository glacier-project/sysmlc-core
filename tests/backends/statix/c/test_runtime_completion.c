/*
 * test_runtime_completion.c - Status helper smoke test.
 *
 * Completion dispatch is generated per statechart after A.0; this runtime-level
 * test keeps the status helper covered under the strict C warning set.
 */

#include "sc/sc_status.h"

#include <assert.h>
#include <string.h>

int main(void)
{
    assert(strcmp(sc_status_str(SC_STATUS_STEP_LIMIT), "SC_STATUS_STEP_LIMIT") == 0);
    assert(strcmp(sc_status_str((sc_status_t)100), "SC_STATUS_UNKNOWN") == 0);
    return 0;
}
