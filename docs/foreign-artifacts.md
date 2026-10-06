# Foreign artifacts

Foreign artifacts provide implementations for model calculations using Python
or C. Backends declare the languages they consume; their build and run commands
expose the corresponding repeatable file flags. Use `--strict-extern` with Statix
to reject an unimplemented calculation during generation, including whole-model
builds.

```text
private import ForeignArtifactBinding::*;
@ForeignArtifact {
    lang = "python";
    files = ("support.py", "helpers.py");
}
```

`lang` must evaluate to a nonempty string, and `files` to a nonempty string or
sequence of strings. Attribute references and other evaluable SysML expressions
are accepted. Relative paths refer to the declaring `.sysml` file's directory.
Declarations on multiple elements or in different documents are collected in
model order. Language tags are normalized, paths become absolute, and identical
file inputs are delivered once.

Explicit flags replace both metadata files and textual representations **in that
language**, before reading those model sources. For example, `--python replacement.py`
works even if the model's original Python file is missing or its representation
is invalid. Repeat `--python` to supply several replacement files. Other languages
continue to resolve from the model.

Python implementations expose top-level synchronous functions. A calculation's
simple name must have one implementation across the supplied modules. Duplicate
function names or module stems are diagnosed before generating code or executing
modules. Foreign files must also have unique output filenames.

C implementations use `--c implementation.c --c_h interface.h`, or equivalent
metadata declarations. The source must expose an ordinary externally visible
function definition, and a declared header must provide its prototype. C syntax
is parsed with Tree-sitter; comments, pointer return types, and function scope
are respected. Preprocessing, type checking, and linking remain the C compiler's
responsibility. Macro-generated function declarations require ordinary explicit
signatures for symbol discovery.

C textual representations generate a source and a guarded companion header.
Includes, macros, typedefs, and type declarations survive in that header; function
bodies become prototypes. The source also declares each exported function before
its definition, after any required type context. Identical helper definitions are emitted once, and
conflicting definitions are errors. Package scaffolding for automatic companions
must contain declarations rather than external global storage definitions; use
explicit source/header files when that contract is unsuitable.

## Library use

`collect_foreign_dependencies()` owns the same replacement and resolution policy
used by the CLI. It returns frozen `ExternalDependency(language, files)` objects
without parsing file symbols. The backend contract passes frozen per-file
`ForeignArtifact(path, lang)` declarations, whose construction also performs no
source reads. Consumers call `interpret_artifacts()` when they need a validated
symbol map. This keeps declaration collection independent of language-specific
interpretation and runtime loading.
