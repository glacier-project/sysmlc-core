package ENUMREJECT {
    private import ScalarValues::*;

    // A structured enumeration (the official ClassificationKind shape,
    // reduced to one field and one literal): the enum def specializes an
    // attribute def, so its literal carries a `:>>` attribute redefinition
    // instead of a single primitive value.
    attribute def Level {
        attribute code : String;
    }
    enum def Structured specializes Level {
        secret {
            :>> code = "secr";
        }
    }
    state def MachineStructuredEnum {
        attribute k : Structured := Structured::secret;
        entry;
            then idle;
        state idle;
    }

    // Mixed declared-value kinds: one literal declares a Real, another a
    // String. Neither the native-scalar rule (all literals share one kind)
    // nor the generated-enum rule (all String, or none valued) applies.
    enum def MixedKind {
        alpha = 1.0;
        beta = "two";
    }
    state def MachineMixedKindEnum {
        attribute v : MixedKind := MixedKind::alpha;
        entry;
            then idle;
        state idle;
    }

    // A literal's declared value is a computed expression, not a bare
    // literal node.
    enum def ComputedDefault {
        alpha = 2.0 + 2.0;
    }
    state def MachineComputedDefaultEnum {
        attribute v : ComputedDefault := ComputedDefault::alpha;
        entry;
            then idle;
        state idle;
    }

    // Two different enum definitions collide after `_c_identifier`
    // sanitization: `LightColor` and `Light_Color` both sanitize to
    // `light_color`.
    enum def LightColor :> String {
        red = "red";
    }
    enum def Light_Color :> String {
        green = "green";
    }
    state def MachineCollidingEnumNames {
        attribute a : LightColor := LightColor::red;
        attribute b : Light_Color := Light_Color::green;
        entry;
            then idle;
        state idle;
    }

    // Relational comparison against a generated (String-valued) enum
    // literal: rejected -- only == and != are supported for symbolic enums.
    enum def RelColor :> String {
        red = "red";
        green = "green";
    }
    state def MachineRelationalLiteral {
        attribute c : RelColor := RelColor::red;
        entry;
            then idle;
        state idle;
        state matched;
        transition first idle if c < RelColor::green then matched;
    }

    // Relational comparison between two symbolic-enum-typed attributes:
    // rejected the same way -- the type-aware check catches this even
    // though neither operand is itself a literal reference.
    state def MachineRelationalAttributes {
        attribute c1 : RelColor := RelColor::red;
        attribute c2 : RelColor := RelColor::green;
        entry;
            then idle;
        state idle;
        state matched;
        transition first idle if c1 < c2 then matched;
    }

    // Relational comparison between two enum-valued *composite fields*
    // (b1.shade < b2.shade): rejected the same way -- both operands are
    // FeatureChainExpressions, exercising the chain-walking branch of the
    // type-aware check, not just the bare-attribute-reference branch
    // MachineRelationalAttributes exercises.
    attribute def Box {
        attribute shade : RelColor = RelColor::red;
    }
    state def MachineRelationalCompositeFields {
        attribute b1 : Box;
        attribute b2 : Box;
        entry;
            then idle;
        state idle;
        state matched;
        transition first idle if b1.shade < b2.shade then matched;
    }
}
