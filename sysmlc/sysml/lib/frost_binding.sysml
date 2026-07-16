package FrostBinding {
    doc /* Connection idiom for routing SysML signals over the Frost
         * network (github.com/glacier-project/frost).
         *
         * A `connect` typed by FrostChannel is realized by the frostifier
         * backend over the generated FrostLink instead of a direct
         * (deterministic) Lingua Franca wire: each signal crossing the
         * channel is delivered by invoking the receiving part's
         * `AsyncMethodNode` through the link, exactly as an external
         * Frost node would. The signals still follow the ordinary
         * routing rules (strict ports, no fan-in, no bidirectional
         * same-name signals), but delivery takes the Frost protocol
         * path: sender adapter -> FrostLink -> receiver adapter ->
         * receiver.
         *
         * Backends without a Frost network (rosetta, quake) reject
         * FrostChannel connections loudly.
         */

    abstract connection def FrostChannel {
        doc /* A part-to-part connection carried by the Frost protocol
             * over the generated FrostLink. Signals crossing it must
             * have all-scalar payloads: delivery is an AsyncMethodNode
             * invocation, and only scalar attributes have data-model
             * parameter nodes. */
    }
}
