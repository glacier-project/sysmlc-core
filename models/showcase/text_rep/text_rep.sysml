package TextRepExample {
    private import ScalarValues::*;
    private import SI::*;

    // -----------------------------------------------------------------------
    // Pure function, implemented inline via Python TextualRepresentation
    // (extracted automatically into the companion external module).
    // -----------------------------------------------------------------------
    calc def addOne {
        in value : Integer;
        return : Integer;

        rep impl language "Python"
        /*
def addOne(value):
    return value + 1
        */
    }

    // -----------------------------------------------------------------------
    // Counter
    // Ticks every second, bumping value via the external addOne calc.
    // Two-state timer pattern (mirrors PendulumSimulation): counting is the
    // waiting state, bumped is the transient state that carries the do
    // action's result back around — avoids a self-loop timer transition.
    // -----------------------------------------------------------------------
    state def Counter {
        attribute value : Integer := 0;

        entry; then counting;

        state counting;
        state bumped;

        transition first counting
            accept after 1 [s]
            do assign value := TextRepExample::addOne(value)
            then bumped;

        transition first bumped then counting;
    }

    part def CounterPart {
        exhibit state : Counter;
    }

    // -----------------------------------------------------------------------
    // Top-level part usage: must itself own a nested part usage to qualify
    // as a top-level part usage (see top_level_part_usages in queries.py) —
    // a bare `part counter : CounterPart;` at package scope is a leaf and
    // would not be selected, falling back to the (wrong) statedef path.
    // -----------------------------------------------------------------------
    part textRepSystem {
        part counter : CounterPart;
    }
}