// Reusable application data declared in a library package.
library package PayloadLibrary {
    private import ScalarValues::*;

    item def LibraryData {
        attribute x : Integer default 7;
        attribute y : Integer default 9;
    }
}

package PayloadConstruction {
    private import ScalarValues::*;
    private import PayloadLibrary::*;

    enum def Mode { idle; busy; }

    item def Data {
        attribute x : Integer default 7;
        attribute y : Integer default 9;
    }
    item def Child :> Data;
    item def Redefined :> Data {
        attribute :>> y default 11;
    }
    item def RedefinedNoValue :> Data {
        attribute :>> y : Integer;
    }
    item def Unvalued {
        attribute n : Integer;
    }
    item def Derived {
        attribute a : Integer default 1;
        attribute b : Integer default a + 1;
    }
    item def Status {
        attribute m : Mode default Mode::busy;
    }
    item def Marker;
    attribute def Sample {
        attribute level : Integer = 3;
        attribute spare : Integer;
    }
    item def Measurement {
        attribute value : Integer default 1;
        attribute sample : Sample;
    }
    attribute def Chain {
        attribute next : Chain[0..1];
    }
    item def Linked {
        attribute chain : Chain;
    }
    item def Traced {
        attribute s : Integer default 0;
        ref occurrence who;
    }
    item def LibraryChild :> LibraryData;
    item def ExplicitItem :> Items::Item {
        attribute x : Integer default 7;
    }
    item def ExplicitItemChild :> ExplicitItem;
    // Redefines the built-in item characteristic without making it data.
    item def SolidAware {
        attribute :>> isSolid;
        attribute w : Integer default 2;
    }
    attribute def Point {
        attribute x : Integer default 1;
        attribute y : Integer default 2;
    }
    item def Located {
        attribute p : Point {
            attribute :>> x default 5;
        }
    }
    // Distinct inherited fields that share the simple name x.
    item def Left {
        attribute x : Integer default 1;
    }
    item def Right {
        attribute x : Integer default 2;
    }
    item def Both :> Left, Right;
    // Both paths inherit the same field v.
    item def Root {
        attribute v : Integer default 3;
    }
    item def RootLeft :> Root;
    item def RootRight :> Root;
    item def Diamond :> RootLeft, RootRight;

    // Each transition sends one constructor form; tests select it by name.
    state def Sender {
        attribute counter : Integer := 0;
        ref part peer;
        port q;
        entry; then s0;
        state s0;
        transition positional first s0
            do send new Data(7, 42) to q then s0;
        transition defaults first s0
            do send new Data() to q then s0;
        transition named first s0
            do send new Data(y = 42) to q then s0;
        transition inheritedDefaults first s0
            do send new Child() to q then s0;
        transition inheritedNamed first s0
            do send new Child(x = 42) to q then s0;
        transition redefined first s0
            do send new Redefined() to q then s0;
        transition redefinedNamed first s0
            do send new Redefined(y = 3) to q then s0;
        transition redefinedNoValue first s0
            do send new RedefinedNoValue() to q then s0;
        transition runtime first s0
            do send new Data(y = counter + 1) to q then s0;
        transition unvalued first s0
            do send new Unvalued() to q then s0;
        transition derivedOmitted first s0
            do send new Derived() to q then s0;
        transition derivedGiven first s0
            do send new Derived(b = 5) to q then s0;
        transition marker first s0
            do send new Marker() to q then s0;
        transition nestedOmitted first s0
            do send new Measurement() to q then s0;
        transition recursiveOmitted first s0
            do send new Linked() to q then s0;
        transition referenceArgument first s0
            do send new Traced(who = peer) to q then s0;
        transition reversed first s0
            do send new Data(y = counter + 1, x = counter + 2) to q then s0;
        transition libraryDefaults first s0
            do send new LibraryData() to q then s0;
        transition libraryNamed first s0
            do send new LibraryData(y = 42) to q then s0;
        transition libraryInherited first s0
            do send new LibraryChild(x = 42) to q then s0;
        transition solidAware first s0
            do send new SolidAware() to q then s0;
        transition explicitItem first s0
            do send new ExplicitItem() to q then s0;
        transition explicitItemChild first s0
            do send new ExplicitItemChild() to q then s0;
        transition usageOverride first s0
            do send new Located() to q then s0;
        transition sharedName first s0
            do send new Both() to q then s0;
        transition diamond first s0
            do send new Diamond() to q then s0;
    }
}
