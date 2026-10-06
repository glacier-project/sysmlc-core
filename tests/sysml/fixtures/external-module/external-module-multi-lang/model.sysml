package MultiLang {
    private import ForeignArtifactBinding::*;
    @ForeignArtifact {
        lang = "python";
        files = ("impl.py");
    }
    @ForeignArtifact {
        lang = "c";
        files = ("impl.c", "impl.h");
    }
}
