package SM15Rep {
    private import ScalarValues::*;
    private import SI::*;
    package P {
        // Same calc def as sm15-external, but the body is inline as a
        // Python textual representation instead of living in ramp.py.
        calc def step {
            in x : Real;
            in dt : Real;
            return : Real;

            rep impl language "Python"
            /*
             * def step(x, dt):
             *     return x + dt
             */
        }
    }
    state def Ramp {
        attribute x : Real := 0.0;
        entry; then run;
        state run;
        transition first run
            accept after 0.1 [s]
            do assign x := P::step(x, 0.1)
            then run;
    }
}
