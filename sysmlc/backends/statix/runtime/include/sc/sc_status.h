#ifndef SC_STATUS_H
#define SC_STATUS_H

/*
 * sc_status.h - Explicit status / return codes.
 *
 * Safety note (Power of 10 rule 7): every public function that can fail returns
 * one of these codes, and callers are expected to check it. SC_STATUS_OK is
 * guaranteed to be 0 so `if (status != SC_STATUS_OK)` is the canonical test.
 */

#ifdef __cplusplus
extern "C" {
#endif

typedef enum sc_status_e {
    SC_STATUS_OK = 0,           /* success                                    */
    SC_STATUS_ERROR,            /* unspecified failure                        */
    SC_STATUS_INVALID_ARGUMENT, /* a NULL pointer or out-of-range argument    */
    SC_STATUS_QUEUE_FULL,       /* event could not be enqueued                */
    SC_STATUS_QUEUE_EMPTY,      /* no event available to dequeue              */
    SC_STATUS_NO_TRANSITION,    /* event did not enable any transition        */
    SC_STATUS_STEP_LIMIT        /* completion micro-step exceeded SC_MAX_RTC_STEPS */
} sc_status_t;

/*
 * Returns a static, never-NULL, human-readable name for a status code.
 *
 * Implemented with a bounded switch (not a table of pointers) so the runtime
 * remains free of function pointers and statically analyzable.
 */
const char *sc_status_str(sc_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* SC_STATUS_H */
