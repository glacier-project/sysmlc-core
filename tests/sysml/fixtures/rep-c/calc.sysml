package CRep {
    calc def increment {
        in x : ScalarValues::Real;
        return : ScalarValues::Real;

        rep impl language "C"
        /*
         * double increment(double x) {
         *     return x + 1.0;
         * }
         */
    }
}
