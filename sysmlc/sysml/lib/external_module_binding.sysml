package ExternalModuleBinding {
    doc /* Metadata for backing a model element with an external source
         * file already written in a target language.
         *
         * An element annotated with ExternalModule declares that its
         * implementation is provided by the file named in `files`, in
         * the language named by `lang`. The path is relative to the
         * declaring `.sysml` file.
         */

    private import ScalarValues::*;

    metadata def ExternalModule {
        doc /* Points a model element at its external source file. */

        /* The target language of the external file, e.g. "python".
         * Declarations for other languages are ignored when resolving
         * for a specific target language. */
        attribute lang : String;

        /* The external source file(s), relative to the declaring
         * .sysml file. Currently only a single file is supported. */
        attribute files : String[*];
    }
}