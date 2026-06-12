package ChargingStation {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import SI::*;
    private import ISQ::DurationValue;

    item def PlugIn;
    item def StopRequest;
    item def Reset;
    item def AuthResult {
        attribute code : Integer;
    }
    item def SessionReport {
        attribute energy : Real;
        attribute sessions : Integer;
    }

    // An EV charging point: connector handshake, authorization with
    // timeout and a bounded retry budget, a three-phase charging profile
    // (ramp-up / bulk / top-off) with thermal derating, and per-session
    // energy accounting. Protocol flavor: payload-coded responses,
    // timeouts, retries, and priority-ordered guards.
    state def ChargingStation {
        port gridPort;

        in attribute targetEnergy : Real default 22.0;
        in attribute rampRate : Real default 4.0;
        in attribute bulkRate : Real default 11.0;
        in attribute topOffRate : Real default 3.0;
        in attribute tempLimit : Real default 70.0;
        in attribute coolThreshold : Real default 55.0;
        in attribute maxAuthRetries : Integer default 2;
        // Rational magnitude on purpose: fractional overrides ("1.5 [s]")
        // can only land in a rational literal.
        attribute authTimeout : DurationValue default 2.0 [s];
        attribute sessionEnergy : Real := 0.0;
        attribute totalEnergy : Real := 0.0;
        attribute temperature : Real := 30.0;
        attribute sessions : Integer := 0;
        attribute authRetries : Integer := 0;

        assert constraint energyAccounting {
            sessionEnergy >= 0.0 and sessionEnergy <= targetEnergy
            and totalEnergy >= 0.0
        }
        // Bulk charging may overshoot by one tick before derating kicks
        // in; the invariant allows that single-step excursion.
        assert constraint thermalEnvelope {
            temperature >= 0.0 and temperature <= tempLimit + 10.0
        }
        assert constraint retryBudget {
            authRetries >= 0 and authRetries <= maxAuthRetries + 1
        }

        entry;
            then idle;

        state idle;

        // Connector handshake: a timed sequence inside its own scope.
        state handshake {
            entry;
                then checkCable;
            state checkCable;
            state lockConnector;
            transition first checkCable accept after 0.3 [s] then lockConnector;
            transition first lockConnector accept after 0.4 [s] then done;
        }

        state authorizing;
        state authRetry;
        state rampUp;
        state bulk;
        state cooling;
        state topOff;
        state finishing;
        state faulted;

        transition first idle accept PlugIn then handshake;
        transition first handshake then authorizing;

        // Authorization: a coded response or a timeout; denials and
        // timeouts consume the retry budget.
        transition first authorizing
            accept r : AuthResult
            if r.code == 1
            do assign authRetries := 0
            then rampUp;
        transition first authorizing
            accept r : AuthResult
            if r.code != 1
            then authRetry;
        transition first authorizing accept after authTimeout then authRetry;

        transition first authRetry
            if authRetries < maxAuthRetries
            do assign authRetries := authRetries + 1
            then authorizing;
        transition first authRetry
            if authRetries >= maxAuthRetries
            do assign authRetries := authRetries + 1
            then faulted;

        // Charging profile: ONE periodic after-self-loop per phase plus
        // guarded eventless hand-offs (priority = declaration order, so
        // thermal derating preempts the energy threshold in `bulk`).
        transition first rampUp
            accept after 1 [s]
            do action {
                assign sessionEnergy :=
                    min(sessionEnergy + rampRate, targetEnergy);
                assign temperature := temperature + 3.0;
            }
            then rampUp;
        transition first rampUp
            if sessionEnergy >= targetEnergy * 0.2
            then bulk;

        transition first bulk
            accept after 1 [s]
            do action {
                assign sessionEnergy :=
                    min(sessionEnergy + bulkRate, targetEnergy);
                assign temperature := temperature + 5.0;
            }
            then bulk;
        transition first bulk if temperature >= tempLimit then cooling;
        transition first bulk
            if sessionEnergy >= targetEnergy * 0.9
            then topOff;

        transition first cooling
            accept after 1 [s]
            do assign temperature := max(temperature - 8.0, 25.0)
            then cooling;
        transition first cooling if temperature <= coolThreshold then bulk;

        transition first topOff
            accept after 1 [s]
            do action {
                assign sessionEnergy :=
                    min(sessionEnergy + topOffRate, targetEnergy);
                assign temperature := max(temperature - 1.0, 25.0);
            }
            then topOff;
        transition first topOff
            if sessionEnergy >= targetEnergy
            then finishing;

        // An operator stop ends the session early from any phase.
        transition first rampUp accept StopRequest then finishing;
        transition first bulk accept StopRequest then finishing;
        transition first cooling accept StopRequest then finishing;
        transition first topOff accept StopRequest then finishing;

        transition first finishing
            accept after 0.5 [s]
            do action {
                assign totalEnergy := totalEnergy + sessionEnergy;
                assign sessions := sessions + 1;
                send new SessionReport(sessionEnergy, sessions) via gridPort;
                assign sessionEnergy := 0.0;
            }
            then idle;

        transition first faulted
            accept Reset
            do assign authRetries := 0
            then idle;
    }
}
