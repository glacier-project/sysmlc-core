package DomainTypes {
    doc /* Structured attribute types for the ICE Laboratory domain. */

    private import ScalarValues::*;

    attribute def PalletStatus {
        doc /* Status of a single pallet on the conveyor belt.
             * Groups the OPC-UA variables that describe a pallet's current state.
             */
        attribute palletNumber : Integer;
        attribute reserved : Integer;
        attribute contentPosition1 : Integer;
        attribute contentPosition2 : Integer;
        attribute contentPosition3 : Integer;
        attribute palletType : Integer;
    }
}
