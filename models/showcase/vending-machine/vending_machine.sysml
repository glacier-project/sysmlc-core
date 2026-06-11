package VendingMachine {
    private import ScalarValues::*;

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
        port dispenser;

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
                send new Dispensed(chosen, credit) via dispenser;
            }
            then idle;
    }
}
