// Bound (`=`) values admitted by the compiled subset: literal constants
// only, read-only at run time. `:=` initial values stay mutable.
package Bindings {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::*;

    enum def Mode { enum idle; enum busy; }

    attribute def Point {
        attribute x : Real = 0.5;
    }

    attribute def Gain {
        attribute value : Real default 1.0;
    }

    attribute def Scaled {
        attribute unit : Real = 1.0;
        attribute twice : Real = unit * 2;
    }

    attribute def Other {
        attribute x : Real default 0.0;
    }

    attribute def Holder {
        attribute point : Point;
    }

    attribute def Rig {
        attribute gain : Gain;
    }

    enum def Light {
        enum red = "r";
        enum green = "g";
    }

    // Valued enumeration literals stand for their values: those must be
    // admitted constants themselves.
    enum def Grade :> Real { enum high = 4.0; enum low = -1.0; }
    enum def Rank :> Real { enum top = Grade::high; }
    enum def Choice :> Integer { enum active = DynamicEnumeration::a; }
    enum def Cycle :> Integer { enum p = Cycle::q; enum q = Cycle::p; }
    enum def Computed :> Real {
        enum peak = NumericalFunctions::max(1.0, 2.0);
    }

    item def Envelope {
        attribute point : Point;
    }

    calc def shift { in p : Point; return : Point; }
    calc def nextHolder { in h : Holder; return : Holder; }
    calc def nextGain { in g : Gain; return : Gain; }

    part def Equipment {
        attribute k : Integer;
        attribute free : Boolean;
        attribute locked : Boolean = false;
    }

    // Every admitted constant form; initial values remain assignable.
    state def Constants {
        attribute flag : Boolean = true;
        attribute count : Integer = 3;
        attribute ratio : Real = 2.5;
        attribute label : String = "on";
        attribute negative : Integer = -4;
        attribute positive : Integer = +4;
        attribute doubleNegative : Integer = - -4;
        attribute mode : Mode = Mode::busy;
        attribute light : Light = Light::green;
        attribute grade : Grade = Grade::low;
        attribute rank : Rank = Rank::top;
        attribute timeout : DurationValue = 2 [min];
        attribute offset : DurationValue = -5 [s];
        attribute limit : Integer default 7;
        attribute pt : Point;
        attribute gain : Gain;
        attribute a : Integer := 1;
        attribute derivedOnce : Integer := a + 1;
        attribute tuned : Integer default := 2;
        attribute bare : Integer;
        entry; then idle;
        state idle {
            entry assign a := 5;
            exit assign tuned := count + 1;
        }
        state finished {
            entry assign bare := limit;
        }
        transition first idle if a == 5 and count == 3 do assign derivedOnce := a then finished;
    }

    // Dynamic bound values are rejected even though syside evaluates them
    // from the initial values of the features they reference.
    state def DynamicExpression {
        attribute a : Integer := 1;
        attribute b : Integer = a + 1;
        entry; then idle;
        state idle;
    }

    state def DynamicReference {
        attribute a : Integer := 1;
        attribute b : Integer = a;
        entry; then idle;
        state idle;
    }

    state def DynamicCall {
        attribute b : Real = NumericalFunctions::max(1.0, 2.0);
        entry; then idle;
        state idle;
    }

    state def DynamicNot {
        attribute b : Boolean = not true;
        entry; then idle;
        state idle;
    }

    state def DynamicDefault {
        attribute a : Integer := 1;
        attribute b : Integer default = a * 2;
        entry; then idle;
        state idle;
    }

    state def DynamicQuantity {
        attribute base : DurationValue := 1 [s];
        attribute delay : DurationValue = base * 2;
        entry; then idle;
        state idle;
    }

    state def DynamicField {
        attribute scaled : Scaled;
        entry; then idle;
        state idle;
    }

    state def DynamicStructured {
        attribute origin : Point;
        attribute pt : Point = origin;
        entry; then idle;
        state idle;
    }

    state def DynamicNested {
        attribute a : Integer := 1;
        entry; then idle;
        state idle {
            attribute local : Integer = a + 1;
        }
    }

    state def DynamicEnumeration {
        attribute a : Integer := 1;
        attribute k : Choice = Choice::active;
        entry; then idle;
        state idle { entry assign a := 5; }
    }

    state def CyclicEnumeration {
        attribute k : Cycle = Cycle::p;
        entry; then idle;
        state idle;
    }

    state def CallEnumeration {
        attribute k : Computed = Computed::peak;
        entry; then idle;
        state idle;
    }

    // Writes to a bound feature, in every action phase and form.
    state def WriteEntry {
        attribute k : Integer = 1;
        entry; then idle;
        state idle { entry assign k := 2; }
    }

    state def WriteEntryBlock {
        attribute k : Integer = 1;
        entry; then idle;
        state idle { entry action { assign k := 2; } }
    }

    state def WriteDo {
        attribute k : Integer = 1;
        entry; then idle;
        state idle { do assign k := 2; }
    }

    state def WriteExit {
        attribute k : Integer = 1;
        entry; then idle;
        state idle { exit action named { assign k := 2; } }
        state finished;
        transition first idle then finished;
    }

    state def WriteEffect {
        attribute k : Integer = 1;
        entry; then idle;
        state idle;
        state finished;
        transition first idle do assign k := 2 then finished;
    }

    state def WriteEffectBlock {
        attribute k : Integer = 1;
        entry; then idle;
        state idle;
        state finished;
        transition first idle do action { assign k := 2; } then finished;
    }

    state def WriteDefault {
        attribute k : Integer default 1;
        entry; then idle;
        state idle { entry assign k := 2; }
    }

    state def WriteNested {
        entry; then outer;
        state outer {
            attribute k : Integer = 1;
            entry; then inner;
            state inner { entry assign k := 2; }
        }
    }

    // Targets are identified by the resolved feature, not its name.
    state def WriteSameName {
        attribute k : Integer = 1;
        ref equipment : Equipment;
        entry; then idle;
        state idle { entry assign equipment.k := 2; }
    }

    state def WriteBoundMember {
        ref equipment : Equipment;
        entry; then idle;
        state idle { entry assign equipment.locked := true; }
    }

    // A bound reference still designates the same occurrence when one of
    // its members changes: only the member's own value is checked.
    state def WriteThroughBoundReference {
        ref spare : Equipment;
        ref equipment : Equipment = spare;
        entry; then idle;
        state idle { entry assign equipment.free := true; }
    }

    state def WriteFixedThroughBoundReference {
        ref spare : Equipment;
        ref equipment : Equipment = spare;
        entry; then idle;
        state idle { entry assign equipment.locked := true; }
    }

    // Redefinitions use the value that applies to the redefining feature;
    // inherited attributes are not materialized, so their bound values
    // are rejected.
    state def FixedBase {
        attribute k : Integer = 1;
    }

    state def DefaultBase {
        attribute j : Integer default 2;
    }

    state def DynamicBase {
        attribute a : Integer := 1;
        attribute b : Integer = a + 1;
    }

    state def InheritedBinding :> FixedBase {
        attribute :>> k;
        entry; then idle;
        state idle;
    }

    state def InheritedFixed :> FixedBase {
        entry; then idle;
        state idle { entry assign k := 2; }
    }

    state def InheritedDefault :> DefaultBase {
        entry; then idle;
        state idle;
    }

    state def InheritedDynamic :> DynamicBase {
        entry; then idle;
        state idle { entry assign a := 5; }
    }

    state def InheritedBySubstate {
        entry; then idle;
        state idle : FixedBase;
    }

    state def OverriddenDefault :> DefaultBase {
        attribute :>> j := 5;
        entry; then idle;
        state idle { entry assign j := 6; }
    }

    state def RedefinedDefault :> DefaultBase {
        attribute :>> j default 7;
        entry; then idle;
        state idle;
    }

    // Replacing a whole structured value must keep its fixed (`=`) fields.
    state def ReplaceFromCall {
        attribute pt : Point;
        entry; then idle;
        state idle { entry assign pt := Bindings::shift(pt); }
    }

    state def ReplaceNestedFromCall {
        attribute h : Holder;
        entry; then idle;
        state idle { entry assign h := Bindings::nextHolder(h); }
    }

    state def ReplaceChainedFromCall {
        item env : Envelope;
        attribute pt : Point;
        entry; then idle;
        state idle { entry assign env.point := Bindings::shift(pt); }
    }

    state def ReplaceFromOtherType {
        attribute pt : Point;
        attribute other : Other;
        entry; then idle;
        state idle { entry assign pt := other; }
    }

    state def ReplaceFromReference {
        attribute pt : Point;
        attribute spare : Point;
        item env : Envelope;
        entry; then idle;
        state idle {
            entry action {
                assign pt := spare;
                assign env.point := pt;
            }
        }
    }

    state def ReplaceFromConstructor {
        attribute pt : Point;
        entry; then idle;
        state idle { entry assign pt := new Point(); }
    }

    // A constructed Holder does not materialize its point's fixed `x`.
    state def ReplaceNestedFromConstructor {
        attribute h : Holder;
        entry; then idle;
        state idle { entry assign h := new Holder(); }
    }

    state def ReplaceDefaultField {
        attribute gain : Gain;
        entry; then idle;
        state idle { entry assign gain := Bindings::nextGain(gain); }
    }

    // A field the usage fixes itself is not kept by a value of its type.
    state def ReplaceLocalFixedField {
        attribute gain : Gain { attribute :>> value = 7.0; }
        attribute spare : Gain;
        entry; then idle;
        state idle { entry assign gain := spare; }
    }

    state def ReplaceNestedLocalFixedField {
        attribute rig : Rig {
            attribute :>> gain { attribute :>> value = 7.0; }
        }
        attribute spare : Rig;
        entry; then idle;
        state idle { entry assign rig := spare; }
    }

    state def ReplaceLocalDefaultField {
        attribute gain : Gain { attribute :>> value default 7.0; }
        attribute spare : Gain;
        entry; then idle;
        state idle { entry assign gain := spare; }
    }

    state def ReplaceEnumeration {
        attribute light : Light := Light::red;
        entry; then idle;
        state idle { entry assign light := Light::green; }
    }
}
