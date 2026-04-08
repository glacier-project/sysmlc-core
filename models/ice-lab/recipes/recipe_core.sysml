package RecipePrimitives {
    doc /* Reusable metadata and action definitions for recipe modeling. */

    private import ScalarValues::*;
    private import ISQ::*;

    action def Recipe {
        doc /* A complete production recipe.
             * Specializations define the full production flow as a sequence
             * of Task usages.
             */
    }

    action def Task {
        doc /* A production task — one step in a recipe.
             * Each task orchestrates a sequence of machine service calls.
             */
    }

    action def MachineService {
        doc /* A machine service — a reusable equipment operation.
             * Orchestrates one or more OPC-UA method calls on a specific
             * equipment interface.
             */
    }

    action def MachineFunction {
        doc /* An atomic OPC-UA method call on equipment. Each machine function maps to exactly
             * one OPC-UA method.
             */
    }

    action def Delay {
        doc /* Pause execution for a specified duration. */
        in attribute duration :> ISQ::duration;
    }

    calc def RandomGenInteger {
        doc /* Generate a random integer in [lower, upper] range. */
        in lower : Integer;
        in upper : Integer;
        return result : Integer;
    }

}
