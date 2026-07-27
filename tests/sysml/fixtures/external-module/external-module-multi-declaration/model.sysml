package MultiDeclaration {
    private import ExternalModuleBinding::*;
    package A {
        @ExternalModule {
            lang = "python";
            files = ("a.py");
        }
    }
    package B {
        @ExternalModule {
            lang = "python";
            files = ("b.py");
        }
    }
}
