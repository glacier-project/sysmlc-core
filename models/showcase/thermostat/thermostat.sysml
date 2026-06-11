package Thermostat {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    state def Thermostat {
        in attribute setpoint : Real default 21.0;
        in attribute hysteresis : Real default 0.5;
        inout attribute temperature : Real := 18.0;

        entry;
            then heating;

        // Closed-loop simulation: ONE periodic after-self-loop per mode
        // drifts the temperature; a guarded EVENTLESS transition (checked
        // on every re-entry) switches modes. Deliberately NOT two parallel
        // `after` transitions: two same-offset timers fire at the same tag
        // and the first reaction's assignment could flip the second's
        // guard, double-setting modes.
        state heating;
        state idle;

        transition first heating
            accept after 1 [s]
            do assign temperature := temperature + 0.8
            then heating;
        // Eventless: evaluated on every (re-)entry of `heating`.
        transition first heating
            if temperature >= setpoint + hysteresis
            then idle;
        transition first idle
            accept after 1 [s]
            do assign temperature := temperature - 0.3
            then idle;
        // Eventless: evaluated on every (re-)entry of `idle`.
        transition first idle
            if temperature <= setpoint - hysteresis
            then heating;
    }
}
