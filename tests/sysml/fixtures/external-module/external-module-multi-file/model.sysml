package MultiFile {
    private import ExternalModuleBinding::*;
    @ExternalModule {
        lang = "python";
        files = ("a.py", "b.py");
    }
}
