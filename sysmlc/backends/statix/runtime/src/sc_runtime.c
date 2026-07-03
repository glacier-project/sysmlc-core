/*
 * sc_runtime.c - Machine-agnostic runtime instance helpers.
 *
 * No recursion, no goto, no function pointers, no dynamic memory. Generated
 * statechart units own dispatch so their guard/action calls can stay file-local
 * and direct.
 */

#include "sc/sc_runtime.h"

sc_status_t sc_runtime_bind(sc_runtime_t *runtime, const sc_machine_t *machine, void *user_data)
{
    if ((runtime == NULL) || (machine == NULL) || (machine->transitions == NULL) ||
        (machine->states == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (machine->initial_state >= machine->state_count) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    runtime->machine = machine;
    runtime->user_data = user_data;
    runtime->current_state = machine->initial_state;
    runtime->initialized = true;
    return SC_STATUS_OK;
}

sc_status_t sc_runtime_get_state(const sc_runtime_t *runtime, sc_state_id_t *out_state)
{
    if ((runtime == NULL) || (out_state == NULL) || (!runtime->initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    *out_state = runtime->current_state;
    return SC_STATUS_OK;
}
