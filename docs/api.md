# API Reference

The core package: model loading, the shared state-machine semantics, the
neutral code generator, and the plugin (`Backend`) contract. The individual
backends document their own APIs in their respective repositories.

<!-- The autodoc directives below are wrapped in `{eval-rst}` fences on
purpose: a bare `{automodule}` MyST fence renders autodoc's generated
reStructuredText as literal text, so the RST escape hatch is required for the
API reference to render. -->

## Core

```{eval-rst}
.. automodule:: sysmlc.errors
.. automodule:: sysmlc.values
.. automodule:: sysmlc.logging
```

## Plugin API

```{eval-rst}
.. automodule:: sysmlc.backends.base
```

## SysML front-end

```{eval-rst}
.. automodule:: sysmlc.sysml.loading
.. automodule:: sysmlc.sysml.queries
.. automodule:: sysmlc.sysml.visitor
.. automodule:: sysmlc.sysml.editing
.. automodule:: sysmlc.sysml.quantities
.. automodule:: sysmlc.sysml.names
.. automodule:: sysmlc.sysml.foreign_artifact.base
.. automodule:: sysmlc.sysml.foreign_artifact.metadata
.. automodule:: sysmlc.sysml.foreign_artifact.text_rep
```

## State-machine semantics

```{eval-rst}
.. automodule:: sysmlc.semantics.statemachine.driver
.. automodule:: sysmlc.semantics.statemachine.facts
.. automodule:: sysmlc.semantics.statemachine.target
.. automodule:: sysmlc.semantics.statemachine.interface
.. automodule:: sysmlc.semantics.statemachine.actions
.. automodule:: sysmlc.semantics.statemachine.transitions
.. automodule:: sysmlc.semantics.statemachine.triggers
.. automodule:: sysmlc.semantics.statemachine.states
.. automodule:: sysmlc.semantics.statemachine.attributes
.. automodule:: sysmlc.semantics.statemachine.constraints
```

## Part systems

```{eval-rst}
.. automodule:: sysmlc.semantics.parts.graph
.. automodule:: sysmlc.semantics.parts.routing
```

## Code generation

```{eval-rst}
.. automodule:: sysmlc.codegen.python
```
