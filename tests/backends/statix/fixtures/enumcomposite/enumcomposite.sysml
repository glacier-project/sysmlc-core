package ENUMCOMPOSITE {
    private import ScalarValues::*;

    // A String-valued enumeration referenced from a composite attribute
    // def's own field -- proves `_register_struct` resolves an enum-valued
    // field through `_scalar_c_type`, and that the generated enum typedef
    // is emitted before the nested struct that uses it (not only before
    // the context struct).
    enum def LightColor :> String {
        red = "red";
        green = "green";
    }

    attribute def Holder {
        attribute color : LightColor = LightColor::red;
    }

    state def MachineEnumComposite {
        attribute box : Holder;
        entry;
            then idle;
        state idle;
        state matched;
        transition first idle if box.color == LightColor::red then matched;
    }
}
