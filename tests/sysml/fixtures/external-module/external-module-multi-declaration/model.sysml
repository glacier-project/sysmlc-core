package MultiDeclaration {
    private import ForeignArtifactBinding::*;
    package A {
        @ForeignArtifact {
            lang = "python";
            files = ("a.py");
        }
    }
    package B {
        @ForeignArtifact {
            lang = "python";
            files = ("b.py");
        }
    }
}
