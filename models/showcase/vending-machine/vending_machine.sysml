package VendingMachine {
    private import ScalarValues::*;
    private import SI::*;

    enum def Product :> String {
        enum cola = "cola";
        enum water = "water";
    }

    item def Coin {
        attribute value : Integer;
    }
    item def Selection {
        attribute product : Product;
    }
    item def Dispensed {
        attribute product : Product;
        attribute change : Integer;
    }

    state def VendingMachine {
        port commPort;

        attribute credit : Integer := 0;
        attribute price : Integer := 3;
        // The default makes `chosen` a declared LF state variable; without
        // one it would be skipped and created dynamically on first assign.
        attribute chosen : Product := Product::water;

        // Runtime-checked invariant: dispensing must never overdraw.
        assert constraint creditNonNegative { credit >= 0 }

        entry;
            then idle;

        state idle;
        state paid;

        transition first idle
            accept coin : Coin
            if credit + coin.value < price
            do assign credit := credit + coin.value
            then idle;
        transition first idle
            accept coin : Coin
            if credit + coin.value >= price
            do assign credit := credit + coin.value
            then paid;
        transition first paid
            accept sel : Selection
            do action {
                assign chosen := sel.product;
                assign credit := credit - price;
                send new Dispensed(chosen, credit) via commPort;
            }
            then idle;
    }

    // Testbench: inserts two Coin(2) payments (totalling 4 >= price 3) then
    // a Selection("cola") at relative 0.1 s intervals.  Expects Dispensed
    // within 5 s of the selection; missing it latches verdict := 1, which
    // violates `testPassed` and aborts with exit 1.
    //
    // Stimulus chain (logical time):
    //   0.1 s  coin1Wait entry → send Coin(2)  [credit 2 < 3, plant stays idle]
    //   0.2 s  coin2Wait entry → send Coin(2)  [credit 4 >= 3, plant → paid]
    //   0.3 s  dispenseWait entry → send Selection("cola")  [plant dispenses]
    //   plant sends Dispensed(…) via commPort → accepted in dispenseWait
    //
    // Selection is sent from dispenseWait's entry so the mode is already
    // active when the plant's Dispensed reply arrives (same microstep as
    // the TrafficLightTest/StopwatchTest pattern).
    state def VendingMachineTest {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port commPort;

        entry; then starting;
        state starting;
        // Entry: send Coin(2) so it arrives in the next microstep after
        // this mode is active -- credit becomes 2 (< 3), plant stays idle.
        state coin1Wait {
            entry send new Coin(2) via commPort;
        }
        // Entry: send second Coin(2) -- credit reaches 4 (>= 3), plant → paid.
        state coin2Wait {
            entry send new Coin(2) via commPort;
        }
        // Entry: send Selection("cola") -- plant is in paid, processes the
        // selection, and sends Dispensed back via commPort at this same tag.
        state dispenseWait {
            entry send new Selection("cola") via commPort;
        }
        state fail {
            entry assign verdict := 1;
        }

        transition first starting
            accept after 0.1 [s]
            then coin1Wait;
        transition first coin1Wait
            accept after 0.1 [s]
            then coin2Wait;
        transition first coin2Wait
            accept after 0.1 [s]
            then dispenseWait;
        transition first dispenseWait accept Dispensed then done;
        transition first dispenseWait accept after 5.0 [s] then fail;
        transition first fail then done;
    }

    part def VendingMachineRig {
        exhibit state plant : VendingMachine;
        exhibit state tb : VendingMachineTest;
    }
}
