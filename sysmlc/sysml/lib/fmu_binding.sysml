package FmuBinding {
    doc /* Metadata for binding a SysML part definition to an external
         * FMU (Functional Mock-up Interface, co-simulation).
         *
         * A part def annotated with FmuImport declares that its instances
         * are realized by the FMU at `path`. The part def's typed ports
         * declare the signal interface: an `out item` is a signal the FMU
         * emits at every communication point, an `in item` is a signal
         * whose payload sets the FMU's inputs. Payload attribute names
         * bind to the FMU's variable names 1:1.
         *
         * The part def's own attributes configure the FMU: each attribute
         * with a literal value binds to the FMU variable of the same name
         * (causality `parameter` or `input`) and is applied once, inside
         * the FMU's initialization mode.
         *
         * A `parameter` variable of variability `tunable` may instead be
         * bound by an `in item` on a port, exactly like an `input`: its
         * signal payload re-sets the variable at each communication point.
         *
         * `exposedParameters` and `exposedVariables` name FMU variables
         * published on the Frost network without a signal/route: exposed
         * variables are read-only probes, exposed parameters are settable
         * knobs. Each becomes a typed data-model node.
         */

    private import ScalarValues::*;

    metadata def FmuImport {
        doc /* Binds a part definition to its co-simulation FMU. */

        /* The .fmu archive, relative to the declaring .sysml file. */
        attribute path : String;

        /* The co-simulation communication interval, in seconds. Omitted,
         * it falls back to the archive's own DefaultExperiment stepSize. */
        attribute stepSize : Real[0..1];

        /* The declared experiment length, in seconds: the generated
         * program's run bound (LF `timeout`) unless overridden on the
         * command line. Omitted, the program runs unbounded. */
        attribute stopTime : Real[0..1];

        /* The relative tolerance passed to the FMU's initialization mode.
         * Omitted, the FMU picks its own. Must be positive. */
        attribute tolerance : Real[0..1];

        /* The FMI start time, in seconds, seeding the FMU's clock at
         * initialization. Omitted, it defaults to 0. Must be finite and
         * non-negative. */
        attribute startTime : Real[0..1];

        /* FMU `parameter`/`input` variables published on the Frost
         * network as settable data-model nodes, without a signal. */
        attribute exposedParameters : String[0..*];

        /* FMU variables (typically `output`/`local`) published on the
         * Frost network as read-only data-model nodes, without a
         * signal. */
        attribute exposedVariables : String[0..*];
    }
}
