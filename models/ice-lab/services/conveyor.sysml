package Conveyor {
    doc /* Closed-loop conveyor belt services (Cell 7, equipment ID: conveyorBelt).*/

    private import ScalarValues::*;
    private import SequenceFunctions::*;
    private import SI::*;
    private import DomainEnums::*;
    private import DomainTypes::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def ReleasePallet :> MachineService {
        doc /* Release a pallet's reservation, making it available for other orders.

             Args:
               palletNumber: ID of the pallet to release.
             */

        in palletNumber : Integer;
        in ref equipment : ConveyorBeltEquipment;

        first start;

        then action callReleasePallet :> equipment.releasePallet {
            in :>> palletNumber = ReleasePallet::palletNumber;
        }

        then done;
    }

    action def MovePalletToMainBelt :> MachineService {
        doc /* Route a pallet back to the main belt (destination 0) to circulate freely.

             Args:
               palletNumber: ID of the pallet to reroute.

             Returns:
               result: true if the PLC accepted the command.
             */

        in palletNumber : Integer;
        in ref equipment : ConveyorBeltEquipment;
        out result : Boolean;

        constant attribute mainBeltDestination : ConveyorDestination = ConveyorDestination::mainBelt;

        first start;

        then action callSetDestination :> equipment.setPalletDestination {
            in :>> palletNumber = MovePalletToMainBelt::palletNumber;
            in constant :>> destination = mainBeltDestination;
        }

        then done;

        bind result = callSetDestination.result;
    }

    action def ClearPartOnPallet :> MachineService {
        doc /* Clear the content register for a pallet position.

             Zeroes the PLC content field — does NOT physically remove a part.
             Use after a robot has already picked the part off the pallet.

             Args:
               palletNumber: ID of the pallet to update.
               position: Pallet slot to clear (1–3).

             Returns:
               result: true if the PLC accepted the command.
             */

        in palletNumber : Integer;
        in position : Integer;
        in ref equipment : ConveyorBeltEquipment;
        out result : Boolean;

        first start;

        then action callClearPart :> equipment.clearPartOnPallet {
            in :>> palletNumber = ClearPartOnPallet::palletNumber;
            in :>> position = ClearPartOnPallet::position;
        }

        then done;

        bind result = callClearPart.result;
    }

    action def ReservePallet :> MachineService {
        doc /* Mark a specific pallet as reserved with the given reservation ID.

             Args:
               palletNumber: ID of the pallet to reserve.
               reservationId: Reservation tag to assign.
             */

        in palletNumber : Integer;
        in reservationId : Integer;
        in ref equipment : ConveyorBeltEquipment;

        first start;

        then action callReservePallet :> equipment.reservePallet {
            in :>> palletNumber = ReservePallet::palletNumber;
            in :>> reservationId = ReservePallet::reservationId;
        }

        then done;
    }

    action def SetPartOnPallet :> MachineService {
        doc /* Write a part code into a pallet's content register at a given position.

             Updates the PLC content field — does NOT physically place a part.
             Use after a robot or operator has already loaded the part.

             Args:
               palletNumber: ID of the pallet to update.
               position: Pallet slot to update (1–3).
               partCode: Integer identifying the part type placed at this position.

             Returns:
               result: true if the PLC accepted the command.
             */

        in palletNumber : Integer;
        in position : Integer;
        in partCode : Integer;
        in ref equipment : ConveyorBeltEquipment;
        out result : Boolean;

        first start;

        then action callSetPart :> equipment.setPartOnPallet {
            in :>> palletNumber = SetPartOnPallet::palletNumber;
            in :>> position = SetPartOnPallet::position;
            in :>> partCode = SetPartOnPallet::partCode;
        }

        then done;

        bind result = callSetPart.result;
    }

    action def CallFreePalletToDestination :> MachineService {
        doc /* Find any unreserved pallet and route it to a destination bay.

             Calls the PLC method to dispatch a free pallet, then polls the
             destination arrival variable until the pallet physically arrives.

             Args:
               destination: Target bay byte code (see ConveyorDestination).
               equipment: The conveyor belt equipment instance.
               palletAtDestination: Reference to the destination arrival attribute
                 on the equipment (e.g. equipment.destinationPalletId_3_1).

             Returns:
               palletNumber: ID (1–10) of the dispatched pallet, or -1 if
                 no free pallet is available.
             */

        in destination : ConveyorDestination;
        in ref equipment : ConveyorBeltEquipment;
        in ref palletAtDestination : Integer;
        out palletNumber : Integer;

        first start;

        then action callFreePallet :> equipment.callFreePalletTo {
            in :>> destination = CallFreePalletToDestination::destination;
        }

        then mWait;
        merge mWait;
        then decide;
            if palletAtDestination == callFreePallet.palletNumber then afterWait;
            else mWait;

        action afterWait;
        then done;

        bind palletNumber = callFreePallet.palletNumber;
    }

    action def CallFreePalletToDestinationWithReservation :> MachineService {
        doc /* Find any unreserved pallet, reserve it, and route to a destination bay.

             Same contract as CallFreePalletToDestination, but the pallet
             is also marked with the given reservationId so other orders cannot
             claim it.

             Args:
               destination: Target bay byte code (see ConveyorDestination).
               reservationId: Reservation tag to mark the pallet as claimed.
               equipment: The conveyor belt equipment instance.
               palletAtDestination: Reference to the destination arrival attribute.

             Returns:
               palletNumber: ID (1–10) of the dispatched pallet, or -1 if none available.
             */

        in destination : ConveyorDestination;
        in reservationId : Integer;
        in ref equipment : ConveyorBeltEquipment;
        in ref palletAtDestination : Integer;
        out palletNumber : Integer;

        first start;

        then action callFreePallet :> equipment.callFreePalletToWithReservation {
            in :>> destination = CallFreePalletToDestinationWithReservation::destination;
            in :>> reservationId = CallFreePalletToDestinationWithReservation::reservationId;
        }

        then mWait;
        merge mWait;
        then decide;
            if palletAtDestination == callFreePallet.palletNumber then afterWait;
            else mWait;

        action afterWait;
        then done;

        bind palletNumber = callFreePallet.palletNumber;
    }

    action def CallFreePalletOfTypeToDestination :> MachineService {
        doc /* Find a free pallet matching a specific pallet type and route to destination.

             Same contract as CallFreePalletToDestination, but filters
             pallets by type before dispatching.

             Args:
               destination: Target bay byte code (see ConveyorDestination).
               palletType: Pallet type identifier to filter available pallets.
               equipment: The conveyor belt equipment instance.
               palletAtDestination: Reference to the destination arrival attribute.

             Returns:
               palletNumber: ID (1–10) of the dispatched pallet, or -1 if none available.
             */

        in destination : ConveyorDestination;
        in palletType : Integer;
        in ref equipment : ConveyorBeltEquipment;
        in ref palletAtDestination : Integer;
        out palletNumber : Integer;

        first start;

        then action callFreePallet :> equipment.callFreePalletOfTypeTo {
            in :>> destination = CallFreePalletOfTypeToDestination::destination;
            in :>> palletType = CallFreePalletOfTypeToDestination::palletType;
        }

        then mWait;
        merge mWait;
        then decide;
            if palletAtDestination == callFreePallet.palletNumber then afterWait;
            else mWait;

        action afterWait;
        then done;

        bind palletNumber = callFreePallet.palletNumber;
    }

    action def CallFreePalletOfTypeToDestinationWithReservation :> MachineService {
        doc /* Find a free pallet matching type, reserve it, and route to destination.

             Combines pallet-type filtering with reservation. Same contract
             as CallFreePalletToDestination.

             Args:
               destination: Target bay byte code (see ConveyorDestination).
               palletType: Pallet type identifier to filter available pallets.
               reservationId: Reservation tag to mark the pallet as claimed.
               equipment: The conveyor belt equipment instance.
               palletAtDestination: Reference to the destination arrival attribute.

             Returns:
               palletNumber: ID (1–10) of the dispatched pallet, or -1 if none available.
             */

        in destination : ConveyorDestination;
        in palletType : Integer;
        in reservationId : Integer;
        in ref equipment : ConveyorBeltEquipment;
        in ref palletAtDestination : Integer;
        out palletNumber : Integer;

        first start;

        then action callFreePallet :> equipment.callFreePalletOfTypeToWithReservation {
            in :>> destination = CallFreePalletOfTypeToDestinationWithReservation::destination;
            in :>> palletType = CallFreePalletOfTypeToDestinationWithReservation::palletType;
            in :>> reservationId = CallFreePalletOfTypeToDestinationWithReservation::reservationId;
        }

        then mWait;
        merge mWait;
        then decide;
            if palletAtDestination == callFreePallet.palletNumber then afterWait;
            else mWait;

        action afterWait;
        then done;

        bind palletNumber = callFreePallet.palletNumber;
    }

    action def SetPalletToDestination :> MachineService {
        doc /* Route an already-known pallet to a destination and wait for arrival.

             Unlike the CallFreePallet* family (which find a free pallet), this
             operates on a specific palletNumber the caller already holds.
             Sends the routing command, then polls the arrival variable until
             the pallet physically arrives.

             Args:
               palletNumber: Pallet ID (1–10) to route.
               destination: Target bay byte code (see ConveyorDestination).
               equipment: The conveyor belt equipment instance.
               palletAtDestination: Reference to the destination arrival attribute
                 on the equipment (e.g. equipment.destinationPalletId_3_1).

             Returns:
               result: true if the PLC accepted the routing command.
             */

        in palletNumber : Integer;
        in destination : ConveyorDestination;
        in ref equipment : ConveyorBeltEquipment;
        in ref palletAtDestination : Integer;
        out result : Boolean;

        first start;

        then action callSetDest :> equipment.setPalletDestination {
            in :>> palletNumber = SetPalletToDestination::palletNumber;
            in :>> destination = SetPalletToDestination::destination;
        }

        then mWait;
        merge mWait;
        then decide;
            if palletAtDestination == SetPalletToDestination::palletNumber then afterWait;
            else mWait;

        action afterWait;
        then done;

        bind result = callSetDest.result;
    }

    action def SetPalletToDestinationWithReservation :> MachineService {
        doc /* Route a known pallet to a destination with reservation, and wait for arrival.

             Same as SetPalletToDestination but also marks the pallet with
             the given reservationId during routing.

             Args:
               palletNumber: Pallet ID (1–10) to route.
               destination: Target bay byte code (see ConveyorDestination).
               reservationId: Reservation tag to mark the pallet as claimed.
               equipment: The conveyor belt equipment instance.
               palletAtDestination: Reference to the destination arrival attribute.

             Returns:
               result: true if the PLC accepted the routing command.
             */

        in palletNumber : Integer;
        in destination : ConveyorDestination;
        in reservationId : Integer;
        in ref equipment : ConveyorBeltEquipment;
        in ref palletAtDestination : Integer;
        out result : Boolean;

        first start;

        then action callSetDest :> equipment.setPalletDestinationWithReservation {
            in :>> palletNumber = SetPalletToDestinationWithReservation::palletNumber;
            in :>> destination = SetPalletToDestinationWithReservation::destination;
            in :>> reservationId = SetPalletToDestinationWithReservation::reservationId;
        }

        then mWait;
        merge mWait;
        then decide;
            if palletAtDestination == SetPalletToDestinationWithReservation::palletNumber then afterWait;
            else mWait;

        action afterWait;
        then done;

        bind result = callSetDest.result;
    }

    action def WaitAckLoadUnloadZone :> MachineService {
        doc /* Signal the operator at bay 5 (load/unload zone) and wait for acknowledgment.

             Operator handshake protocol: turn on bay light (value 2), reset
             the ack button, poll until operator presses ack, then turn off
             the light.

             Args:
               equipment: The conveyor belt equipment instance.
             */

        in ref equipment : ConveyorBeltEquipment;

        first start;

        then assign equipment.bay5Light := BayLightState::signaling;

        then assign equipment.ackLoadUnloadZone := false;

        then mWaitAck;
        merge mWaitAck;
        then decide;
            if equipment.ackLoadUnloadZone == true then afterAck;
            else mWaitAck;

        action afterAck;

        then assign equipment.bay5Light := BayLightState::off;

        then done;
    }

    action def WaitAckBay :> MachineService {
        doc /* Signal the operator at a numbered bay and wait for acknowledgment.

             Generic version of the bay handshake protocol: turn on bay light
             (value 2), reset the ack button, poll until operator presses ack,
             then turn off the light. The caller passes references to the
             specific bay light and ack button attributes on the equipment.

             Args:
               equipment: The conveyor belt equipment instance.
               bayLight: Reference to the bay light attribute
                 (e.g. equipment.bay3Light).
               ackButton: Reference to the ack button attribute
                 (e.g. equipment.ackBay3).
             */

        in ref equipment : ConveyorBeltEquipment;
        in ref bayLight : Integer;
        in ref ackButton : Boolean;

        first start;

        then assign bayLight := BayLightState::signaling;

        then assign ackButton := false;

        then mWaitAck;
        merge mWaitAck;
        then decide;
            if ackButton == true then afterAck;
            else mWaitAck;

        action afterAck;

        then assign bayLight := BayLightState::off;

        then done;
    }


    action def ReadPalletContent :> MachineService {
        doc /* Read the content value at a specific position on a pallet.

             Scans the equipment's pallet status array to find the pallet
             matching palletNumber, then returns the content code at the
             given position (1, 2, or 3).

             Args:
               palletNumber: ID (1–10) of the pallet to read.
               position: Pallet slot to read (1–3, see PalletSlot).
               equipment: The conveyor belt equipment instance.

             Returns:
               result: Content code at the requested position (0 = empty).
             */

        in palletNumber : Integer;
        in position : Integer;
        in ref equipment : ConveyorBeltEquipment;
        out result : Integer;

        attribute content : Integer := 0;

        first start;

        then for p in equipment.pallets {
            action checkNumber;
            then decide;
                if p.palletNumber == ReadPalletContent::palletNumber then readContent;
                else skipPallet;

            action readContent;
            then decide;
                if position == PalletSlot::pos1 then readPos1;
                else checkPos2;

            action readPos1 { assign content := p.contentPosition1; }
            then mEnd;

            action checkPos2;
            then decide;
                if position == PalletSlot::pos2 then readPos2;
                else readPos3;

            action readPos2 { assign content := p.contentPosition2; }
            then mEnd;

            action readPos3 { assign content := p.contentPosition3; }
            then mEnd;

            action skipPallet;
            then mEnd;

            merge mEnd;
        }

        then done;

        bind result = content;
    }

    action def CheckPalletMatch {
        doc /* Check whether a single pallet matches a content+type configuration.

             Generic sub-action used by all ReserveFreePallet* variants.
             Takes a structured reference to a PalletStatus instance.

             Sentinel values for contentPosN:
               -1: Skip this position (no check).
               -2: Wildcard — matches any non-zero value.
               Other: Exact match required.

             palletType sentinel:
               -1: Skip type check.
               Other: Exact match required.
             */

        in ref pallet : PalletStatus;
        in contentPos1 : Integer;
        in contentPos2 : Integer;
        in contentPos3 : Integer;
        in palletType : Integer;
        out matched : Boolean;

        attribute contentMatch : Boolean := true;

        // Step 0: Check if pallet is already reserved
        first start;
        then decide;
            if pallet.reserved != ReservationKind::unreserved then noMatch;
            else checkPos1Gate;

        // --- Position 1 ---
        action checkPos1Gate;
        then decide;
            if contentPos1 == PalletContentFilter::dontCare then mPos1; // skip
            else checkPos1;

        action checkPos1;
        then decide;
            if contentPos1 == PalletContentFilter::anyNonEmpty then checkPos1Wild;
            else checkPos1Exact;

        action checkPos1Wild;
        then decide;
            if pallet.contentPosition1 == PalletContentFilter::empty then noMatch;
            else mPos1;

        action checkPos1Exact;
        then decide;
            if pallet.contentPosition1 != contentPos1 then noMatch;
            else mPos1;

        merge mPos1;

        // --- Position 2 ---
        then decide;
            if contentPos2 == PalletContentFilter::dontCare then mPos2; // skip
            else checkPos2;

        action checkPos2;
        then decide;
            if contentPos2 == PalletContentFilter::anyNonEmpty then checkPos2Wild;
            else checkPos2Exact;

        action checkPos2Wild;
        then decide;
            if pallet.contentPosition2 == PalletContentFilter::empty then noMatch;
            else mPos2;

        action checkPos2Exact;
        then decide;
            if pallet.contentPosition2 != contentPos2 then noMatch;
            else mPos2;

        merge mPos2;

        // --- Position 3 ---
        then decide;
            if contentPos3 == PalletContentFilter::dontCare then mPos3; // skip
            else checkPos3;

        action checkPos3;
        then decide;
            if contentPos3 == PalletContentFilter::anyNonEmpty then checkPos3Wild;
            else checkPos3Exact;

        action checkPos3Wild;
        then decide;
            if pallet.contentPosition3 == PalletContentFilter::empty then noMatch;
            else mPos3;

        action checkPos3Exact;
        then decide;
            if pallet.contentPosition3 != contentPos3 then noMatch;
            else mPos3;

        merge mPos3;

        // --- Type check ---
        then decide;
            if palletType == PalletContentFilter::dontCare then yesMatch; // skip type check
            else checkTypeGate;

        action checkTypeGate;
        then decide;
            if pallet.palletType != palletType then noMatch;
            else yesMatch;

        // --- Outcomes ---
        action yesMatch { assign contentMatch := true; }
        then mEnd;

        action noMatch { assign contentMatch := false; }
        then mEnd;

        merge mEnd;
        then done;

        bind matched = contentMatch;
    }

    action def ReserveFreePallet :> MachineService {
        doc /* Reserve pallets whose content matches a given configuration.

             Two-phase algorithm:
               Phase 1 — Scan pallets 1–10 via for loop: for each pallet, call
               CheckPalletMatch. Matching pallets are reserved (reservationId=2).
               Guard condition (j < palletNumber) prevents over-reservation.
               Phase 2 — Request new pallets: if Phase 1 did not find enough
               matches, repeatedly call the warehouse to dispatch new free pallets
               (with reservation). For each new pallet, wait for arrival, prompt
               the operator to load the configuration, wait for ack, then update
               the content registers.

             Sentinel values for contentPosN:
               -1: Skip this position (do not check or set content).

             Args:
               palletNumber: Number of pallets to reserve (target count).
               contentPos1: Required content code at position 1, or -1 to skip.
               contentPos2: Required content code at position 2, or -1 to skip.
               contentPos3: Required content code at position 3, or -1 to skip.
               equipment: The conveyor belt equipment instance.
               warehouseEquipment: The warehouse equipment instance (for operator messages).

             Returns:
               palletIds: Sequence of reserved pallet IDs (length = palletNumber).
             */

        in palletNumber : Integer;
        in contentPos1 : Integer;
        in contentPos2 : Integer;
        in contentPos3 : Integer;
        in ref equipment : ConveyorBeltEquipment;
        in ref warehouseEquipment : WarehouseEquipment;
        out palletIds : Integer[0..10] := ();

        attribute j : Integer := 0;
        attribute palletId : Integer := 0;

        // --- Phase 1: Scan pallets via for loop ---
        // ReserveFreePallet does not use -2 wildcard or type check,
        // so palletType=-1 (skip) is passed to CheckPalletMatch.

        first start;

        then for p in equipment.pallets {
            action check : CheckPalletMatch {
                in ref :>> pallet = p;
                in :>> contentPos1 = ReserveFreePallet::contentPos1;
                in :>> contentPos2 = ReserveFreePallet::contentPos2;
                in :>> contentPos3 = ReserveFreePallet::contentPos3;
                in constant :>> palletType = PalletContentFilter::dontCare;
            }
            then decide;
                if check.matched and j < palletNumber then doReserve;
                else skipPallet;

            action doReserve;
            then action reserve :> equipment.reservePallet {
                in :>> palletNumber = p.palletNumber;
                in constant :>> reservationId = ReservationKind::processing;
            }
            then assign palletIds := including(palletIds, p.palletNumber);
            then assign j := j + 1;
            then mEnd;

            action skipPallet;
            then mEnd;

            merge mEnd;
        }

        // --- Phase 2: Request new free pallets with operator UI ---

        then afterPhase1;

        action afterPhase1;
        then mPhase2;

        merge mPhase2;
        then decide;
            if j < palletNumber then mRetry;
            else afterPhase2;

        merge mRetry;
        then action callFreePallet :> equipment.callFreePalletToWithReservation {
            in constant :>> destination = ConveyorDestination::bay5_warehouse;
            in constant :>> reservationId = ReservationKind::transport;
        }
        then assign palletId := callFreePallet.palletNumber;

        then decide;
            if palletId == -1 then sleepRetry;
            else skipSleep;

        action sleepRetry : Delay {
            in :>> duration = 1 [s];
        }
        then mSleep;

        action skipSleep;
        then mSleep;

        merge mSleep;

        then decide;
            if palletId != -1 then waitForArrival;
            else mRetry; // back-edge

        // Wait for pallet to arrive at bay 5
        action waitForArrival;
        then mWaitArrival;
        merge mWaitArrival;
        then decide;
            if equipment.destinationPalletId_5 == palletId then operatorUI;
            else mWaitArrival;

        // Operator UI: show message, wait ack, set content
        action operatorUI;
        then action showLoadMessage :> warehouseEquipment.showMessage {
            in :>> msg = "Please load the configuration on the pallet, then press the ack button";
        }

        then assign equipment.bay5Light := BayLightState::signaling;

        then assign equipment.ackLoadUnloadZone := false;

        then mWaitAck;
        merge mWaitAck;
        then decide;
            if equipment.ackLoadUnloadZone == true then afterAck;
            else mWaitAck;

        action afterAck;

        then assign equipment.bay5Light := BayLightState::off;

        // Set content registers for each non-skipped position
        then decide;
            if contentPos1 != PalletContentFilter::dontCare then setPartPos1;
            else skipPart1;

        action setPartPos1;
        then action callSetPart1 :> equipment.setPartOnPallet {
            in :>> palletNumber = palletId;
            in constant :>> position = PalletSlot::pos1;
            in :>> partCode = ReserveFreePallet::contentPos1;
        }
        then mPart1;

        action skipPart1;
        then mPart1;

        merge mPart1;

        then decide;
            if contentPos2 != PalletContentFilter::dontCare then setPartPos2;
            else skipPart2;

        action setPartPos2;
        then action callSetPart2 :> equipment.setPartOnPallet {
            in :>> palletNumber = palletId;
            in constant :>> position = PalletSlot::pos2;
            in :>> partCode = ReserveFreePallet::contentPos2;
        }
        then mPart2;

        action skipPart2;
        then mPart2;

        merge mPart2;

        then decide;
            if contentPos3 != PalletContentFilter::dontCare then setPartPos3;
            else skipPart3;

        action setPartPos3;
        then action callSetPart3 :> equipment.setPartOnPallet {
            in :>> palletNumber = palletId;
            in constant :>> position = PalletSlot::pos3;
            in :>> partCode = ReserveFreePallet::contentPos3;
        }
        then mPart3;

        action skipPart3;
        then mPart3;

        merge mPart3;

        then assign palletIds := including(palletIds, palletId);
        then assign j := j + 1;
        then mPhase2;   // back-edge

        action afterPhase2;
        then done;
    }

    action def ReserveFreePalletOfType :> MachineService {
        doc /* Reserve pallets matching content configuration AND pallet type.

             Same two-phase algorithm as ReserveFreePallet, but Phase 1 also
             checks the pallet's type register and Phase 2 requests type-filtered
             pallets from the warehouse.

             Phase 1 — Scan pallets 1–10 via for loop: CheckPalletMatch with
             type checking enabled.
             Phase 2 — Request new pallets: call callFreePalletOfTypeToWithReservation
             in a retry loop until enough pallets are obtained.

             Sentinel values for contentPosN:
               -1: Skip this position (do not check or set content).

             Args:
               palletNumber: Number of pallets to reserve (target count).
               contentPos1: Required content code at position 1, or -1 to skip.
               contentPos2: Required content code at position 2, or -1 to skip.
               contentPos3: Required content code at position 3, or -1 to skip.
               palletType: Required pallet type, or -1 to skip type check.
               equipment: The conveyor belt equipment instance.

             Returns:
               palletIds: Sequence of reserved pallet IDs (length = palletNumber).
             */

        in palletNumber : Integer;
        in contentPos1 : Integer;
        in contentPos2 : Integer;
        in contentPos3 : Integer;
        in palletType : Integer;
        in ref equipment : ConveyorBeltEquipment;
        out palletIds : Integer[0..10] := ();

        attribute j : Integer := 0;
        attribute palletId : Integer := 0;

        // --- Phase 1: Scan pallets via for loop ---

        first start;

        then for p in equipment.pallets {
            action check : CheckPalletMatch {
                in ref :>> pallet = p;
                in :>> contentPos1 = ReserveFreePalletOfType::contentPos1;
                in :>> contentPos2 = ReserveFreePalletOfType::contentPos2;
                in :>> contentPos3 = ReserveFreePalletOfType::contentPos3;
                in :>> palletType = ReserveFreePalletOfType::palletType;
            }
            then decide;
                if check.matched and j < palletNumber then doReserve;
                else skipPallet;

            action doReserve;
            then action reserve :> equipment.reservePallet {
                in :>> palletNumber = p.palletNumber;
                in constant :>> reservationId = ReservationKind::processing;
            }
            then assign palletIds := including(palletIds, p.palletNumber);
            then assign j := j + 1;
            then mEnd;

            action skipPallet;
            then mEnd;

            merge mEnd;
        }

        // --- Phase 2: Request new free pallets of type (retry loop) ---

        then afterPhase1;

        action afterPhase1;
        then mPhase2;

        merge mPhase2;
        then decide;
            if j < palletNumber then mRetry;
            else afterPhase2;

        merge mRetry;
        then action callFreePallet :> equipment.callFreePalletOfTypeToWithReservation {
            in constant :>> destination = ConveyorDestination::bay5_warehouse;
            in constant :>> reservationId = ReservationKind::transport;
            in :>> palletType = ReserveFreePalletOfType::palletType;
        }
        then assign palletId := callFreePallet.palletNumber;

        then decide;
            if palletId == -1 then sleepRetry;
            else skipSleep;

        action sleepRetry : Delay {
            in :>> duration = 1 [s];
        }
        then mSleep;

        action skipSleep;
        then mSleep;

        merge mSleep;

        then decide;
            if palletId != -1 then afterRetry;
            else mRetry;   // back-edge

        action afterRetry;
        then assign palletIds := including(palletIds, palletId);
        then assign j := j + 1;
        then mPhase2;   // back-edge

        action afterPhase2;
        then done;
    }

    action def ReserveFreePallet2 :> MachineService {
        doc /* Reserve pallets with wildcard content matching and random generation.

             Same two-phase algorithm as ReserveFreePallet, but adds support
             for the -2 wildcard sentinel:
               -1: Skip this position entirely (no check, no set).
               -2: Wildcard — in Phase 1, matches any non-zero content value;
                   in Phase 2, generates a random value in [1, 3] for new pallets.

             Phase 1 — Scan pallets 1–10 via for loop: CheckPalletMatch handles
             the -2 wildcard semantics.
             Phase 2 — Request new pallets with operator UI: wait for arrival,
             generate random values for -2 positions, prompt operator, wait ack,
             set content registers, route to main belt.

             Args:
               palletNumber: Number of pallets to reserve (target count).
               contentPos1: Required content code at position 1, -1 to skip, -2 for wildcard.
               contentPos2: Required content code at position 2, -1 to skip, -2 for wildcard.
               contentPos3: Required content code at position 3, -1 to skip, -2 for wildcard.
               equipment: The conveyor belt equipment instance.
               warehouseEquipment: The warehouse equipment instance (for operator messages).

             Returns:
               palletIds: Sequence of reserved pallet IDs (length = palletNumber).
             */

        in palletNumber : Integer;
        in contentPos1 : Integer;
        in contentPos2 : Integer;
        in contentPos3 : Integer;
        in ref equipment : ConveyorBeltEquipment;
        in ref warehouseEquipment : WarehouseEquipment;
        out palletIds : Integer[0..10] := ();

        attribute j : Integer := 0;
        attribute palletId : Integer := 0;
        attribute rContentPos1 : Integer := 0;
        attribute rContentPos2 : Integer := 0;
        attribute rContentPos3 : Integer := 0;

        // --- Phase 1: Scan pallets via for loop ---
        // palletType=-1 (skip type check) since this variant has no type filter.

        first start;

        then for p in equipment.pallets {
            action check : CheckPalletMatch {
                in ref :>> pallet = p;
                in :>> contentPos1 = ReserveFreePallet2::contentPos1;
                in :>> contentPos2 = ReserveFreePallet2::contentPos2;
                in :>> contentPos3 = ReserveFreePallet2::contentPos3;
                in constant :>> palletType = PalletContentFilter::dontCare;
            }
            then decide;
                if check.matched and j < palletNumber then doReserve;
                else skipPallet;

            action doReserve;
            then action reserve :> equipment.reservePallet {
                in :>> palletNumber = p.palletNumber;
                in constant :>> reservationId = ReservationKind::processing;
            }
            then assign palletIds := including(palletIds, p.palletNumber);
            then assign j := j + 1;
            then mEnd;

            action skipPallet;
            then mEnd;

            merge mEnd;
        }

        // --- Phase 2: Request new free pallets with operator UI + random ---

        then afterPhase1;

        action afterPhase1;
        then mPhase2;

        merge mPhase2;
        then decide;
            if j < palletNumber then mRetry;
            else afterPhase2;

        merge mRetry;
        then action callFreePallet :> equipment.callFreePalletToWithReservation {
            in constant :>> destination = ConveyorDestination::bay5_warehouse;
            in constant :>> reservationId = ReservationKind::transport;
        }
        then assign palletId := callFreePallet.palletNumber;

        then decide;
            if palletId == -1 then sleepRetry;
            else skipSleep;

        action sleepRetry : Delay {
            in :>> duration = 1 [s];
        }
        then mSleep;

        action skipSleep;
        then mSleep;

        merge mSleep;

        then decide;
            if palletId != -1 then waitForArrival;
            else mRetry; // back-edge

        // Wait for pallet to arrive at bay 5
        action waitForArrival;
        then assign equipment.ackLoadUnloadZone := false;

        then mWaitArrival;
        merge mWaitArrival;
        then decide;
            if equipment.destinationPalletId_5 == palletId then resolveContent;
            else mWaitArrival;

        // Resolve content values: -2 -> random [1,3], else keep as-is
        action resolveContent;

        then decide;
            if contentPos1 == PalletContentFilter::anyNonEmpty then genRandom1;
            else skipRandom1;

        action genRandom1;
        then calc randomGen1 : RandomGenInteger {
            in constant :>> lower = 1;
            in constant :>> upper = 3;
        }
        then assign rContentPos1 := randomGen1.result;
        then mRandom1;

        action skipRandom1 {
            assign rContentPos1 := contentPos1;
        }
        then mRandom1;

        merge mRandom1;

        then decide;
            if contentPos2 == PalletContentFilter::anyNonEmpty then genRandom2;
            else skipRandom2;

        action genRandom2;
        then calc randomGen2 : RandomGenInteger {
            in constant :>> lower = 1;
            in constant :>> upper = 3;
        }
        then assign rContentPos2 := randomGen2.result;
        then mRandom2;

        action skipRandom2 {
            assign rContentPos2 := contentPos2;
        }
        then mRandom2;

        merge mRandom2;

        then decide;
            if contentPos3 == PalletContentFilter::anyNonEmpty then genRandom3;
            else skipRandom3;

        action genRandom3;
        then calc randomGen3 : RandomGenInteger {
            in constant :>> lower = 1;
            in constant :>> upper = 3;
        }
        then assign rContentPos3 := randomGen3.result;
        then mRandom3;

        action skipRandom3 {
            assign rContentPos3 := contentPos3;
        }
        then mRandom3;

        merge mRandom3;

        // Operator UI: show message, wait ack
        then action showLoadMessage :> warehouseEquipment.showMessage {
            in :>> msg = "Please load the configuration on the pallet, then press the ack button";
        }

        then assign equipment.bay5Light := BayLightState::signaling;

        then mWaitAck;
        merge mWaitAck;
        then decide;
            if equipment.ackLoadUnloadZone == true then afterAck;
            else mWaitAck;

        action afterAck;

        then assign equipment.bay5Light := BayLightState::off;

        // Set content registers for each non-skipped position
        then decide;
            if rContentPos1 != PalletContentFilter::dontCare then setPartPos1;
            else skipPart1;

        action setPartPos1;
        then action callSetPart1 :> equipment.setPartOnPallet {
            in :>> palletNumber = palletId;
            in constant :>> position = PalletSlot::pos1;
            in :>> partCode = rContentPos1;
        }
        then mPart1;

        action skipPart1;
        then mPart1;

        merge mPart1;

        then decide;
            if rContentPos2 != PalletContentFilter::dontCare then setPartPos2;
            else skipPart2;

        action setPartPos2;
        then action callSetPart2 :> equipment.setPartOnPallet {
            in :>> palletNumber = palletId;
            in constant :>> position = PalletSlot::pos2;
            in :>> partCode = rContentPos2;
        }
        then mPart2;

        action skipPart2;
        then mPart2;

        merge mPart2;

        then decide;
            if rContentPos3 != PalletContentFilter::dontCare then setPartPos3;
            else skipPart3;

        action setPartPos3;
        then action callSetPart3 :> equipment.setPartOnPallet {
            in :>> palletNumber = palletId;
            in constant :>> position = PalletSlot::pos3;
            in :>> partCode = rContentPos3;
        }
        then mPart3;

        action skipPart3;
        then mPart3;

        merge mPart3;

        // Route to main belt
        then action routeToMainBelt :> equipment.setPalletDestination {
            in :>> palletNumber = palletId;
            in constant :>> destination = ConveyorDestination::mainBelt;
        }

        then assign palletIds := including(palletIds, palletId);
        then assign j := j + 1;
        then mPhase2; // back-edge

        action afterPhase2;
        then done;
    }

    action def ReserveFreePalletOfType2 :> MachineService {
        doc /* Reserve pallets matching pallet type + content with wildcard support.

             Combines the pallet-type filtering of ReserveFreePalletOfType with
             the -2 wildcard semantics of ReserveFreePallet2. Phase 2 requests
             type-filtered pallets from the warehouse; wildcard positions get
             random values in [1, 3] for newly loaded pallets.

             Phase 1 — Scan pallets 1–10 via for loop: CheckPalletMatch with
             type checking and wildcard support enabled.
             Phase 2 — Request new pallets: call callFreePalletOfTypeToWithReservation
             in a retry loop until enough pallets are obtained.

             Args:
               palletNumber: Number of pallets to reserve (target count).
               contentPos1: Required content code at position 1, -1 to skip, -2 for wildcard.
               contentPos2: Required content code at position 2, -1 to skip, -2 for wildcard.
               contentPos3: Required content code at position 3, -1 to skip, -2 for wildcard.
               palletType: Required pallet type, or -1 to skip type check.
               equipment: The conveyor belt equipment instance.

             Returns:
               palletIds: Sequence of reserved pallet IDs (length = palletNumber).
             */

        in palletNumber : Integer;
        in contentPos1 : Integer;
        in contentPos2 : Integer;
        in contentPos3 : Integer;
        in palletType : Integer;
        in ref equipment : ConveyorBeltEquipment;
        out palletIds : Integer[0..10] := ();

        attribute j : Integer := 0;
        attribute palletId : Integer := 0;

        // --- Phase 1: Scan pallets via for loop ---

        first start;

        then for p in equipment.pallets {
            action check : CheckPalletMatch {
                in ref :>> pallet = p;
                in :>> contentPos1 = ReserveFreePalletOfType2::contentPos1;
                in :>> contentPos2 = ReserveFreePalletOfType2::contentPos2;
                in :>> contentPos3 = ReserveFreePalletOfType2::contentPos3;
                in :>> palletType = ReserveFreePalletOfType2::palletType;
            }
            then decide;
                if check.matched and j < palletNumber then doReserve;
                else skipPallet;

            action doReserve;
            then action reserve :> equipment.reservePallet {
                in :>> palletNumber = p.palletNumber;
                in constant :>> reservationId = ReservationKind::processing;
            }
            then assign palletIds := including(palletIds, p.palletNumber);
            then assign j := j + 1;
            then mEnd;

            action skipPallet;
            then mEnd;

            merge mEnd;
        }

        // --- Phase 2: Request new free pallets of type (retry loop) ---

        then afterPhase1;

        action afterPhase1;
        then mPhase2;

        merge mPhase2;
        then decide;
            if j < palletNumber then mRetry;
            else afterPhase2;

        merge mRetry;
        then action callFreePallet :> equipment.callFreePalletOfTypeToWithReservation {
            in constant :>> destination = ConveyorDestination::bay5_warehouse;
            in constant :>> reservationId = ReservationKind::transport;
            in :>> palletType = ReserveFreePalletOfType2::palletType;
        }
        then assign palletId := callFreePallet.palletNumber;

        then decide;
            if palletId == -1 then sleepRetry;
            else skipSleep;

        action sleepRetry : Delay {
            in :>> duration = 1 [s];
        }
        then mSleep;

        action skipSleep;
        then mSleep;

        merge mSleep;

        then decide;
            if palletId != -1 then afterRetry;
            else mRetry; // back-edge

        action afterRetry;
        then assign palletIds := including(palletIds, palletId);
        then assign j := j + 1;
        then mPhase2; // back-edge

        action afterPhase2;
        then done;
    }
}
