# SysML v2 → sismic: construct mapping

How each SysML v2 state-machine construct is translated into an executable
[sismic](https://sismic.readthedocs.io/) statechart.

## Support at a glance

Status of every construct, implemented and planned. **Done**: implemented.
**Done, to refine**: implemented, with a known gap detailed in the section's
Limitation callout. **Being replaced**: implemented, but the current emission
was found unfaithful. **Not yet**: not implemented.

| Construct                                                            | Status          | Notes                                                                                                                      |
| -------------------------------------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `state def` → statechart                                             | Done            |                                                                                                                            |
| `entry; then X` → `initial`                                          | Done, to refine | only simple state targets are currently supported. Qualified-name targets (nested-state paths) are rejected (coverage gap) |
| `first start then X` → `initial`                                     | Done, to refine | only simple state targets are currently supported. Qualified-name targets (nested-state paths) are rejected (coverage gap) |
| leaf `state` → basic state                                           | Done            |                                                                                                                            |
| composite `state` → nested state                                     | Done            |                                                                                                                            |
| `parallel` → orthogonal state                                        | Done            |                                                                                                                            |
| `then done` → final state                                            | Done            |                                                                                                                            |
| attribute value → `preamble`                                         | Done, to refine | `=`/`constant` guarantees not enforced; bound expressions snapshotted                                                      |
| composite attribute → namespace                                      | Done, to refine | usage-site redefinitions and bindings ignored                                                                              |
| bare `transition first A then B`                                     | Done            |                                                                                                                            |
| transition into a nested state (`then running.hot`)                  | Done            | enters the composite bypassing its default entry; documented pair still missing in this file                               |
| transition spellings (`then X;`, `accept E then X;` in a state body) | Done, to refine | the standalone `first A then B;` succession (no `transition` keyword) is silently dropped                                  |
| `accept E` (signal) → `event`                                        | Done, to refine | `via` port dropped; payload binding not readable                                                                           |
| `if` guard → `guard`                                                 | Done            |                                                                                                                            |
| `accept after` (time)                                                | Being replaced  | emitted as an `after()` guard today, unfaithful with `if` guards and self-loops; one-shot event replacement designed       |
| `accept at` (time)                                                   | Not yet         | rejected today; replacement designed                                                                                       |
| `accept when` (change)                                               | Not yet         | rejected today; replacement designed                                                                                       |
| `entry`/`exit` actions                                               | Done, to refine | referencing form (`entry helper;`) silently dropped                                                                        |
| `do` action (terminating body)                                       | Done            | ongoing bodies (`accept`, loops) rejected for now                                                                          |
| transition effect → `action`                                         | Done, to refine | referencing form silently dropped                                                                                          |
| `send` → `send(...)`                                                 | Done, to refine | `via` port dropped                                                                                                         |
| enum literals → Python `Enum`                                        | Not yet         |                                                                                                                            |
| referenced / performed actions                                       | Not yet         | `entry helper;`, `do A;`, perform in any action slot: fixes the silent drops of the entry/exit and effect rows             |
| readable accept payload                                              | Not yet         | payload references emitted as `event.<field>`: fixes the `accept E` row's gap                                              |
| `assert constraint` in a state                                       | Not yet         | asserted constraint usages become sismic `invariants`, checked while the state is active                                   |
| `assert constraint` on a transition                                  | Not yet         | asserted constraint usages become sismic preconditions/postconditions, checked around the firing                           |
| exhibit / entry point                                                | Not yet         | build the statechart from an exhibited state usage, not only a `state def`                                                 |
| submachine reuse (`state s1 : Sub;`)                                 | Not yet         | a state usage typed by a `state def`; today it is **silently flattened** to a leaf, losing the def's whole content         |
| ongoing `do` activities                                              | Not yet         | event-gated and time-gated do-loops, mixed control loops                                                                   |
| multi-machine simulation                                             | Not yet         | addressing, dispatch-once and scheduling over sismic's `bind()`                                                            |

## How to read this

- **Each pair** shows the SysML input first, then its emitted YAML, with a one-line rule alongside.
- A ***Why*** line (italic) explains a mapping that isn't obvious.
- A **Boundary** callout (blockquote, ⚠️) marks a construct the generator
  deliberately **rejects** (fail-loud) rather than emit something unfaithful.
- A **Limitation** callout (blockquote, ⚠️) marks a construct the generator
  **accepts and emits**, but whose translation is **imperfect** in some cases: a
  known gap to refine, not a rejection.
- A ***Spec:*** tag cites the clauses the construct's SysML semantics come from,
  in the OMG specifications: [KerML](https://www.omg.org/spec/KerML/) v1.0
  Beta 4 and [SysML v2](https://www.omg.org/spec/SysML/) v2.0 Part 1.

Every rule is a real **SysML input → emitted YAML output** pair, drawn from the
`models/sm-examples/` corpus and its generated `output/sismic/` artifacts.
Generate outputs with `uv run python examples/run_sismic.py <example>`, which builds every state def in the example and writes
`output/sismic/<example>/<Machine>.{yaml,puml}`. One exception, marked 🚧 in
place: the time and change trigger sections of chapter 3 (3.4 to 3.6) are
**work in progress** and show the upcoming replacement design instead of the
current generator output, because the previously documented mapping was found
unfaithful.

## The statechart at a glance

**What a sismic statechart gives you:**

- a `name`, an optional `preamble` (Python run once to define the context: its
  variables and classes), and a single `root state`
- **states** form a tree. The generator uses four of sismic's state kinds:
  - **basic**: a leaf
  - **composite**: nested, with an `initial` substate
  - **orthogonal**: `parallel` regions, all active at once
  - **final**
- every state can run code `on entry` and `on exit`
- **transitions** carry up to three optional parts: an `event` (trigger), a
  `guard` (boolean condition), and an `action` (effect)
- **built-ins** for guards and actions: `after(seconds)` in guards, and
  `send("Event", key=value, delay=D)` in actions (payload fields readable in
  guards as `event.key`; with `delay`, a one-shot event delivered `D` time
  units later)
- **execution** is run-to-completion: each *macro step* consumes at most one
  event and runs every transition it triggers, plus stabilization (entering
  initial substates), until the configuration is stable. Within a step, sismic
  orders transitions:
  - **eventless** before **event-triggered**
  - **internal** events (raised by `send`) before **external** ones (from the host)
  - **inner-first**: deeper source states before outer ones
  - higher **priority** among transitions leaving the same state

The translation works on two levels at once. **Structure** is the state tree
(the `state def` with its states and transitions). **Emitted code** is SysML
expressions and actions turned into Python source strings placed into sismic's
`guard`, `action`, `on entry`, `on exit`, and `preamble`.

A small but representative machine makes the shape concrete (a purpose-built
showcase; every other pair in this doc comes from the corpus). It has an
attribute, an entry into a nested composite, an accepted event, a guarded exit,
and a final state:

```sysml
item def Start;

state def Machine {
    attribute cycles : Integer := 0;

    entry; then idle;
    state idle;
    state running {
        entry; then warming;
        state warming {
            entry assign cycles := cycles + 1;
        }
        state ready;
        transition first warming then ready;
    }

    transition first idle accept Start then running;
    transition first running if cycles > 0 then done;
}
```

```yaml
statechart:
  name: Machine
  preamble: cycles = 0
  root state:
    initial: idle
    name: Machine
    states:
    - name: idle
      transitions:
      - {event: Start, target: running}
    - initial: running::warming
      name: running
      states:
      - name: running::warming
        on entry: cycles = cycles + 1
        transitions:
        - {target: running::ready}
      - {name: running::ready}
      transitions:
      - {guard: cycles > 0, target: done}
    - {name: done, type: final}
```

Every construct here is detailed below: the `attribute` becomes the `preamble`,
`accept` an `event`, `if` a `guard`, `then done` a `final` state, and `running`
a nested composite state.

______________________________________________________________________

## 1. States

### 1.1 `state def` → statechart root state

*Corpus: [`sm01-helloworld`](../models/sm-examples/sm01-helloworld/sm01.sysml)*

*Spec: SysML 7.18.1 (states overview), 7.18.2 (state definitions and usages)*

A `state def` becomes a sismic statechart. Its name appears twice: as the statechart
`name` and the `root state` name. The root is a **composite** state (an
**orthogonal** state when the def is `parallel`, Section 1.5).

```sysml
state def Machine { ... }
```

```yaml
statechart:
  name: Machine
  root state:
    name: Machine
    # initial, states, ...
```

*Why:* a sismic statechart is a single tree under one `root state`, so the def,
as the whole machine, maps to that root. It is **composite** because it holds
substates: a state's kind comes from whether it has children, so the inner
childless `idle`/`running` are basic leaves.

### 1.2 `entry; then X;` → the root's `initial`

*Corpus: [`sm01-helloworld`](../models/sm-examples/sm01-helloworld/sm01.sysml)*

*Spec: SysML 7.18.1, 7.18.2 (entry action and target succession); KerML 9.2.11.1
(state performances)*

In SysML, `entry` is the action a state runs when it is entered, and `then idle`
is a succession from it to `idle`. Here the `entry` action is empty, so
`entry; then idle;` carries no behavior and simply makes `idle` the first
substate to become active. It maps to the composite state's `initial`.

```sysml
state def Machine {
    entry; then idle;
    state idle;
    ...
}
```

```yaml
root state:
  initial: idle
  name: Machine
  # ...
```

*Why:* `entry` is the state's **entry action** slot, not a separate node; here
it is simply empty, so `entry; then X;` only selects the initial substate. Given
a body, the same slot runs code on entry (`entry action` / `entry assign`,
Section 4), and it can carry a body and a `then` together.

> ⚠️ **Boundary:** the initial target must currently be a simple state name.
> Qualified-name targets that reference nested states are rejected.
> This is a coverage gap.

### 1.3 `first start then X;` → the root's `initial`

*Corpus: [`sm01-helloworld`](../models/sm-examples/sm01-helloworld/sm01.sysml)*

*Spec: SysML 7.18.1, 7.18.2 (entry action and target succession); KerML 9.2.11.1
(state performances)*

SysML provides an alternative spelling for selecting the first active substate:
`first start then idle;`. The `start` performance represents the activation of
the enclosing state, and the succession to `idle` makes that substate become
active first. This carries the same meaning as `entry; then idle;` and maps to
the composite state's `initial`.

```sysml
state def Machine {
    first start then idle;
    state idle;
    ...
}
```

```yaml
root state:
  initial: idle
  name: Machine
  # ...
```

*Why:* every SysML state has an implicit `start` performance.
`first start then X;` expresses the transition from this default initial point to the actual first substate `X`.

> ⚠️ **Boundary:** the initial target must currently be a simple state name.
> Qualified-name targets that reference nested states are rejected.
> This is a coverage gap.

### 1.4 leaf `state` → basic state

*Corpus: [`sm01-helloworld`](../models/sm-examples/sm01-helloworld/sm01.sysml)*

*Spec: SysML 7.18.2 (state definitions and usages)*

A leaf `state` (one with **no substates**) becomes a **basic** state. It may
carry a body of `entry`/`do`/`exit` actions. With no actions it is a bare
`{name: ...}`; with actions, the basic state carries `on entry`/`on exit`
(Section 4).

```sysml
state running;
```

```yaml
- {name: running}
```

### 1.5 composite `state X { ... }` → nested composite state

*Corpus: [`sm08-nested-composite`](../models/sm-examples/sm08-nested-composite/sm08.sysml)*

*Spec: SysML 7.18.1 (state decomposition), 7.18.2 (state definitions and
usages)*

In SysML, a composite state is a `state` **with substates**: its body nests them,
a default entry, and inner transitions, so it is a state machine inside a state. It
becomes a nested **composite** state with its own `initial` (its entry-selected
substate) and `states`; like a leaf, it also carries any `entry`/`do`/`exit`
actions of its own as `on entry`/`on exit` (Section 4). Composites nest
arbitrarily deep, and each state's name is its **full path from the def**, joined
with `::`.

```sysml
state def MachineNested {
    entry; then idle;
    state idle;
    state running {
        entry; then warming;
        state warming;
        state hot;
        transition first warming then hot;
    }
    ...
}
```

```yaml
- initial: running::warming
  name: running
  states:
  - name: running::warming
    transitions:
    - {target: running::hot}
  - {name: running::hot}
```

*Why:* each nested state's sismic name is its full parent chain, not just its
own identifier: `warming` inside `running` is named `running::warming` (and
`running::warming::low` one level deeper). That keeps state names unique when two
composites reuse the same identifiers, like `groupA::active` vs `groupB::active`.

### 1.6 `parallel` → orthogonal state

*Corpus: [`sm09-parallel`](../models/sm-examples/sm09-parallel/sm09.sysml)*

*Spec: SysML 7.18.1 (parallel states), 7.18.2 (the `parallel` keyword)*

In SysML, the `parallel` keyword marks a state whose substates are **concurrent
regions**, all active at once, instead of one-at-a-time substates. It applies to
a whole `state def` (a parallel root) and to a nested `state X` alike. Either
becomes an **orthogonal state**: its regions are listed under `parallel states`,
and each region is itself a composite state with its own `initial`. Like other
states, an orthogonal state can also carry its own `entry`/`do`/`exit` actions as
`on entry`/`on exit` (Section 4).

```sysml
state def MachineParallel parallel {
    state lights {
        entry; then off;
        state off;
        state on;
        transition first off then on;
    }
    state sound {
        entry; then silent;
        state silent;
        state beeping;
        transition first silent then beeping;
    }
}
```

```yaml
root state:
  name: MachineParallel
  parallel states:
  - initial: lights::off
    name: lights
    states:
    - name: lights::off
      transitions:
      - {target: lights::on}
    - {name: lights::on}
  - initial: sound::silent
    name: sound
    states:
    - name: sound::silent
      transitions:
      - {target: sound::beeping}
    - {name: sound::beeping}
```

The same applies to a **nested** `state X parallel { ... }` inside an ordinary
def: it becomes a `- name: X` orthogonal state, with its region names prefixed
(e.g. `dual::lights::off`).

*Why:* in the YAML the orthogonal `root state` has **no `initial:`**, while each
region (`lights`, `sound`) keeps its own. The regions run **concurrently** (both
active at once), so there is no single substate for the orthogonal state to begin
in. A plain composite state, by contrast, has one active substate at a time, so
it does need a single `initial`.

### 1.7 `then done` → final state

*Corpus: [`sm10-done`](../models/sm-examples/sm10-done/sm10.sysml)*

*Spec: SysML 7.18.3 (transition usages: `done`)*

In SysML, `then done` targets `done`, the standard completion state: reaching it
marks the enclosing state (the whole machine, or a composite) as finished. It
becomes a sismic **final state** (`type: final`), named for its scope: `done` at
the root, `running::done` inside the `running` composite.

```sysml
state def MachineRootDone {
    entry; then idle;
    state idle;
    state running;
    transition first idle then running;
    transition first running then done;
}
```

```yaml
statechart:
  name: MachineRootDone
  root state:
    initial: idle
    name: MachineRootDone
    states:
    - name: idle
      transitions:
      - {target: running}
    - name: running
      transitions:
      - {target: done}
    - {name: done, type: final}
```

*Why:* every `then done` in the same scope shares a **single** final state.
What reaching that final state means depends on where the scope sits:

- **At the root** (`done`): the run is **finished**. Sismic empties the active
  configuration and sets `interpreter.final` to `True`, and that flag is how a
  run reports completion to whatever drives it (a simulation loop, an
  orchestrator). Without a root final state a machine can still settle, with no
  transition left to fire, but it stays in an active state and `final` stays
  `False`: quiescent, yet never "finished", so a driver polling `final` waits
  forever.
- **Inside a composite** (`running::done`): only that composite is finished.
  The machine stays alive: `running` itself stays active, and an outer
  transition leaving `running` still fires, but only after the inner region
  reaches `running::done`. This is exactly SysML's rule: a transition to `done`
  marks the source as the final state of the containing state's performance
  without terminating the machine, and an un-triggered transition out of a
  state may fire only once that state has completed. Sismic produces the same
  firing order without any completion check: **inner-first** ordering defers
  the outer eventless transition as long as something deeper can still fire,
  and the dead-end `running::done` leaf is what leaves nothing deeper to fire.
- **In a parallel state**: each region is its own scope, so each reaches its
  **own** `<region>::done`. One region finishing finishes neither the other
  regions nor the machine.

______________________________________________________________________

## 2. Attributes

### 2.1 `attribute` value → `preamble`

*Corpus: [`sm04-assignment`](../models/sm-examples/sm04-assignment/sm04.sysml), [`sm13-time-trigger`](../models/sm-examples/sm13-time-trigger/sm13.sysml)*

*Spec: KerML 7.4.11, 8.3.4.10.2 (feature values); SysML 7.6.3 (`constant`
modifier), 7.9.2 (time-varying values), 7.13.4 (feature values)*

**SysML** gives an attribute a value in several forms, each with its own
meaning; an attribute may also declare no value:

| SysML form                                 | meaning                                                          |
| ------------------------------------------ | ---------------------------------------------------------------- |
| `attribute x := 2;`                        | **initial**: `x` starts at 2 and may change during the run       |
| `attribute x = 2;`                         | **bound**: `x` equals the expression's result for its whole life |
| `attribute x default 2;` (= `default = 2`) | **default**: `x` is 2 unless a specializing usage redefines it   |
| `attribute x default := 2;`                | **default initial**: the start value, unless redefined           |
| `constant attribute x = 2;`                | **constant**: `x` keeps one single value over its whole life     |
| `attribute x : Integer;`                   | **no value**: left unspecified                                   |

Note that **bound** and **constant** constrain different axes: `=` ties the value
to an *expression*, `constant` ties the value
across *time*. With a literal the two coincide.

**The generator** flattens every valued form to the same thing: a plain,
**mutable Python variable**, one `preamble` line `name = value` per attribute
(newline-joined when there are several). A Python variable is exactly SysML's
`:=`, a start value that may change; the other forms are approximated **as if
they were `:=`**: their value is kept, the rest of their meaning is dropped
(limitation below). An attribute with **no value** emits no line at all.

```sysml
attribute counter : Integer := 0;
```

```yaml
preamble: counter = 0
```

A **quantity** attribute (typed by a quantity value type such as
`DurationValue`, its value carrying a unit) is evaluated to a single number in
**SI base units**, so time triggers and guards work with a plain number
(Sections 3.4 and 3.5):

```sysml
attribute pickDuration : DurationValue default 2 [min];
```

```yaml
preamble: pickDuration = 120.0
```

> ⚠️ **Limitation:** everything is emitted as if declared `:=`. The run-time
> guarantees of **`=`** (permanent equality) and **`constant`** (immutability)
> are **not enforced**: both stay ordinary mutable variables, and `syside check`
> does not flag a write to either, so `constant attribute x = 2` followed by
> `assign x := 5` silently ends at `5`, where SysML fixes it at `2`. A bound
> expression is also **snapshotted, not tracked**: `attribute x = y + 1` becomes
> the one-time preamble line `x = y + 1`, so a later change to `y` does not
> update `x`, where SysML keeps the equation alive. This flattening will need
> refining if models start relying on those guarantees.

### 2.2 composite attribute → `SimpleNamespace` tree

*Corpus: [`sm05-chained-references`](../models/sm-examples/sm05-chained-references/sm05.sysml)*

*Spec: SysML 7.7.2 (attribute definitions and usages), 7.6.6 (feature chains),
7.17.9 (assignment targets); KerML 8.3.4.10.2 (initial values require variable
features)*

**SysML**: an attribute is **composite** when its type is an `attribute def`
that owns attributes; defs nest arbitrarily (a `Box` holding an `Inner`).
Inside an `attribute def` a field takes its value with `=` or `default`, never
`:=`: an initial value is only legal on a feature whose value can vary over
time, and the fields of an attribute def cannot vary. The machine reads the
structure through **feature chains** (`box.inner.z`), and it may reassign an
attribute **as a whole** (`assign box := spare`), composite or scalar alike.
What it can never do is write **into** the structure through a chain
(`assign box.inner.z := 1.0`): an assignment's target must evaluate to an
*occurrence* whose referent feature varies over time, and an attribute value is
not an occurrence. The structure's **fields** are therefore read-only by the
model's own rules (`syside check` rejects both the `:=` field and the chain
write). Statically, though, a usage may **redefine** a field's value
(`attribute pt : PointD { :>> x = 1.0; }`), choosing what the field is for that
usage before the run; only `default` values may be overridden, a bound `=`
field cannot.

**The generator** binds the attribute in the `preamble` to a `SimpleNamespace`
tree mirroring its def: one keyword per field, valued from the **definition's**
field values, recursively. A nested def becomes a nested namespace; a quantity
field collapses to its SI base value (`attribute t : DurationValue = 2 [min];`
gives `t=120.0`). When at least one composite is bound, the import line
`from types import SimpleNamespace` is prepended to the `preamble`. Feature
chains in guards and actions are emitted unchanged and resolve
against the bound object.

```sysml
attribute def Inner {
    attribute z : Real = 0.25;
}

attribute def Box {
    attribute inner : Inner;
}

state def MachineChainNested {
    attribute box : Box;
    entry;
        then idle;
    state idle;
    state running;
    transition first idle if box.inner.z > 0.0 then running;
}
```

```yaml
statechart:
  name: MachineChainNested
  preamble: "from types import SimpleNamespace\nbox = SimpleNamespace(inner=SimpleNamespace(z=0.25))"
  root state:
    initial: idle
    name: MachineChainNested
    states:
    - name: idle
      transitions:
      - {guard: box.inner.z > 0.0, target: running}
    - {name: running}
```

*Why:* an emitted chain like `box.inner.z` only evaluates if `box` is a real
Python object with an `inner` attribute; a `SimpleNamespace` provides exactly
that dotted access. Building it **once, at preamble time,** is enough because
the model itself guarantees the built tree never mutates: its fields cannot be
written (above), and a whole-attribute reassignment only rebinds the name to
another tree, which is exactly what the emitted Python does (`assign box := spare` becomes `box = spare`).

> ⚠️ **Boundary:** a field with **no value** anywhere in the def tree is
> **rejected** fail-loud (`Composite attribute field 'y' has no value to bind; give it a default.`). A scalar attribute with no value just stays unbound
> (Section 2.1), but a composite must be **constructed**, and a namespace
> cannot carry a hole.

> ⚠️ **Limitation:** the namespace is built from the definition's field values
> **alone**; any value given at the **usage site** is silently ignored. Both
> forms: a body redefinition (`attribute pt : Point { :>> x = 1.0; }`, legal
> over a `default` field) still emits the def's `x=0.5`, so a guard tuned by
> the redefinition misfires (a machine that should reach `running` stays in
> `idle`); and a whole-value binding (`attribute pt2 : Point = origin;`) emits
> a fresh namespace built from the defaults instead of the binding (in SysML
> `pt2` *is* `origin`; in the emitted Python they are two distinct objects that
> merely start equal).

______________________________________________________________________

## 3. Transitions, triggers & guards

A SysML `transition` connects a source state (`first A`) to a target state
(`then B`), and carries up to three optional parts: an **accepter** (`accept`),
a **guard** (`if`), and an **effect** (`do`). The accepter is the rich part: in
SysML it fires the transition on a **signal** (`accept E`), a **time**
(`accept after <d>`, `accept at <t>`), or a **change** (`accept when <cond>`).

The trap in this mapping is a semantic one. In SysML all three accepter kinds
are the same thing: a **one-shot signal occurrence**. A time or change trigger
does not *test a condition*; it **sends a signal** (in KerML,
`TimeSignal` is a kind of `ChangeSignal`), at most once per activation of the
source state, and a delivered signal is **consumed**, whether or not the `if`
guard lets the transition fire.
Sismic has consume-once semantics in exactly one place: the `event` slot. A
sismic `guard` is the opposite: a plain boolean expression **re-evaluated at
every macro step** the source is active, memoryless, with nothing to consume.

So every accepter maps to something sismic consumes exactly once:

- a **signal** accepter (`accept E`) → `event` (3.2);
- a **time** accepter (`accept after <d>`, `accept at <t>`) → a uniquely named
  **delayed internal event**, armed `on entry` (3.4, 3.5);
- a **change** accepter (`accept when <cond>`) → an **armed flag** plus a
  transition pair that fires or consumes at most once per activation (3.6);
- an **`if`** guard → the `guard` slot, conjoined with the machinery above;
- the **effect** → the `action` (Section 4).

Folding a time or change accepter into the `guard` slot instead is faithful
only for the bare distinct-target forms, where firing vacates the source and
the condition is seen at most once. The moment an `if` guard or a self-loop keeps
the source active past the delivery instant, the still-true guard re-offers an occurrence
SysML has already consumed: a guard `after(2) and g` fires on a
7-second-stale deadline when `g` rises late. Sections 3.4 and 3.6 each open
with their half of this problem.

> 🚧 **Work in progress:** the time and change trigger mapping in this
> chapter is being replaced. The mapping this doc previously described, and
> the one the builder still emits today (`accept after <d>` →
> `{guard: after(<seconds>)}`, with `at`/`when` and `after ... if` rejected
> fail-loud), was found unfaithful for exactly the reason above: the guard is
> re-evaluated every step, so it re-offers occurrences SysML has already consumed. Sections
> 3.4, 3.5 and 3.6 therefore document the **upcoming replacement design**,
> not the current emitter output.

### 3.1 `transition first A then B` → `{target: B}`

*Corpus: [`sm01-helloworld`](../models/sm-examples/sm01-helloworld/sm01.sysml)*

*Spec: SysML 7.18.3 (transition usages); KerML 9.2.10.1 (transition
performances), 9.2.11.1 (state performances)*

A bare transition (no accepter, no guard) is an **eventless transition**: it
fires as soon as `A`'s work is done.

```sysml
state def Machine {
    entry;
        then idle;
    state idle;
    state running;

    transition first idle then running;
}
```

```yaml
statechart:
  name: Machine
  root state:
    initial: idle
    name: Machine
    states:
    - name: idle
      transitions:
      - {target: running}
    - {name: running}
```

### 3.2 `accept E [via port]` → `{event: E}`

*Corpus: [`sm02-event-trigger`](../models/sm-examples/sm02-event-trigger/sm02.sysml)*

*Spec: SysML 7.17.8 (accept action usages), 7.18.3 (transition accepter); KerML
9.2.11.1 (triggers)*

In SysML, an **accepter** is an `accept E` clause between the transition's source
(`first`) and target (`then`). It makes the transition **event-triggered**:
where the eventless transition above fires on its own once the source completes,
an accepter holds the transition until an incoming signal of the accepted
**item/signal type** `E` arrives. It maps to sismic's `event` slot, named by that
type, so the running machine leaves `idle` only when an event named `Tick` is
delivered to it. Of the three accepter kinds, this is the one sismic represents
natively: the `event` slot is consume-once by construction, so a delivered
`Tick` fires at most one transition and is then gone, even when an `if` guard
rejects it.

```sysml
item def Tick;

state def Machine {
    port commPort;
    entry;
        then idle;
    state idle;
    state running;

    transition first idle accept Tick via commPort then running;
}
```

```yaml
statechart:
  name: Machine
  root state:
    initial: idle
    name: Machine
    states:
    - name: idle
      transitions:
      - {event: Tick, target: running}
    - {name: running}
```

That event reaches the machine through one of sismic's two event queues. From
**outside**, the host feeds the **external** queue (`interpreter.queue('Tick')`),
the way a test or driver drives the machine. From **inside**, a `send` action
raises the event on the **internal** queue (`send new Tick(...)` →
`send("Tick")`, Section 4), so a machine can fire its own `accept` (a
single-machine self-send). Internal events are processed before external ones.

*Why:* the event is the **type** name (`Tick`), not the optional payload
binding. Naming the payload (`accept reading : Tick`) and omitting the port
(`accept Tick`) both still yield `event: Tick`: all three forms emit the same
transition.

> ⚠️ **Limitation:** the `via commPort` receiver is **dropped**; events match by
> name alone. A port only matters for cross-machine routing: when several state
> machines are simulated together, the port addresses *which* machine receives
> the transfer. A single statechart has nothing to route between.

> ⚠️ **Limitation:** referencing the payload binding (`accept reading : Reading`
> then `if reading.value > 0.5`) is **not supported yet**: the reference is
> emitted as-is and fails at simulation (`name 'reading' is not defined`).
> Planned support: emit payload references as sismic's `event.<field>`
> (here `event.value > 0.5`).

### 3.3 `if <expr>` → `{guard: <python>}`

*Corpus: [`sm03-guard`](../models/sm-examples/sm03-guard/sm03.sysml)*

*Spec: SysML 7.18.3 (transition guards); KerML 9.2.10.1 (guard evaluations)*

In SysML, a **guard** is an `if <expr>` clause on a transition: a boolean
condition that must hold for it to fire. With no accepter the transition stays
**eventless**, but becomes **conditional**: where the bare transition above fires
the moment its source completes, a guarded one fires only once the source is
active **and** the guard is true. It maps to sismic's `guard` slot and the condition
is emitted as a Python expression. The names the guard references are the
machine's attributes, already bound in the `preamble` (Section 2.1).

```sysml
state def MachineRef {
    attribute enabled : Boolean := true;
    entry;
        then idle;
    state idle;
    state running;

    transition first idle if enabled then running;
}
```

```yaml
statechart:
  name: MachineRef
  preamble: enabled = True
  root state:
    initial: idle
    name: MachineRef
    states:
    - name: idle
      transitions:
      - {guard: enabled, target: running}
    - {name: running}
```

*Why:* the guard is **re-evaluated at every macro step** while the source is
active: false only means "not yet". With no accepter there is nothing to
consume, so this matches SysML's untriggered-transition rule exactly.

### 3.4 **WiP** `accept after <duration>` → one-shot delayed event

*Corpus: [`sm13-time-trigger`](../models/sm-examples/sm13-time-trigger/sm13.sysml)*

*Spec: SysML 7.17.8 (time triggers); KerML 9.2.14 (`TriggerAfter`,
`TimeSignal`), 9.2.13 (Observation)*

**The problem.** In SysML, `accept after d` arms **one** `TimeSignal` per
activation of the source state, and KerML defines its condition
as the clock equality `signalClock.currentTime == signalTime`: a **spike**
that occurs once, at the deadline, and is consumed on delivery. Sismic's
built-in `after(d)` guard is the opposite shape, a **step**: literally
`time - d >= entry time`, true at the deadline and forever after, re-checked
every macro step. The two coincide only when firing vacates the source at the
deadline. Compose with an `if` guard and they split: under `after(2) and (g)`
the transition still fires when `g` first rises 7 seconds past the deadline, while in SysML the signal occurred at the deadline, met a false
guard, was consumed, and nothing may fire later in that activation.

**The mapping.** The deadline becomes a real sismic event. On every entry the
source state increments a per-state **activation counter** and schedules a
uniquely named internal event carrying it; the transition triggers on that
event, with a counter check conjoined into the guard. The duration is
converted to **SI seconds** (quantity values, Section 2.1) and becomes the
event's `delay`. Delivery happens
at the first macro step at or past the deadline, exactly once; if the guard is
false at delivery, the event is consumed and the transition never fires late.

```sysml
state def MachineAfterMinutes {
    entry;
        then idle;
    state idle;
    state running;

    transition first idle accept after 2 [min] then running;
    transition first running then done;
}
```

```yaml
statechart:
  name: MachineAfterMinutes
  preamble: _n_idle = 0
  root state:
    initial: idle
    name: MachineAfterMinutes
    states:
    - name: idle
      on entry: |
        _n_idle = _n_idle + 1
        send("_tick_idle_t1", n=_n_idle, delay=120.0)
      transitions:
      - {event: _tick_idle_t1, guard: event.n == _n_idle, target: running}
    - name: running
      transitions:
      - {target: done}
    - {name: done, type: final}
```

An attribute or chained duration works the same way: the value is initialized
in the `preamble` and referenced by name in the `delay`:

```sysml
state def MachineAfterAttribute {
    attribute pickDuration : DurationValue default 2 [min];
    entry;
        then idle;
    state idle;
    state running;

    transition first idle accept after pickDuration then running;
    transition first running then done;
}
```

```yaml
statechart:
  name: MachineAfterAttribute
  preamble: |
    pickDuration = 120.0
    _n_idle = 0
  root state:
    initial: idle
    name: MachineAfterAttribute
    states:
    - name: idle
      on entry: |
        _n_idle = _n_idle + 1
        send("_tick_idle_t1", n=_n_idle, delay=pickDuration)
      transitions:
      - {event: _tick_idle_t1, guard: event.n == _n_idle, target: running}
    - name: running
      transitions:
      - {target: done}
    - {name: done, type: final}
```

And `accept after ... if <guard>`: the `if`
guard is conjoined after the counter check, and a deadline that arrives while
the guard is false is consumed, which is exactly the SysML behavior:

```sysml
state def MachineAfterGuard {
    attribute ready : Boolean := false;
    entry;
        then idle;
    state idle;
    state running;

    transition first idle accept after 5 [s] if ready then running;
}
```

```yaml
statechart:
  name: MachineAfterGuard
  preamble: |
    ready = False
    _n_idle = 0
  root state:
    initial: idle
    name: MachineAfterGuard
    states:
    - name: idle
      on entry: |
        _n_idle = _n_idle + 1
        send("_tick_idle_t1", n=_n_idle, delay=5.0)
      transitions:
      - {event: _tick_idle_t1, guard: event.n == _n_idle and (ready), target: running}
    - {name: running}
```

*Why the counter:* sismic never cancels a scheduled event when its sending
state exits. Without the check, leaving `idle` before the deadline and
re-entering it later leaves a **stale tick** in the queue, which would fire
the transition at the old deadline instead of the new one. The
counter stamps every tick with the activation that armed it; a stale tick
matches no guard, is consumed by an empty step, and is gone. Self-loops get
periodic behavior for free: each re-entry bumps the counter and schedules a
fresh tick, and every `execute()` call terminates.

*Why:* a time trigger is an *accepter* in SysML and now maps to a real sismic
**event**, recovering the one-shot, consumed-on-delivery semantics. Only the
bare distinct-target form was ever observationally equivalent under the old
`after(...)` guard; the event encoding is emitted uniformly so there is one
mechanism and one story.

> ⚠️ **Reserved names:** `_tick_*` event names and `_n_*` context names belong
> to the generator. A model attribute or signal colliding with a
> reserved prefix is rejected fail-loud.

> ⚠️ **Boundary:** a zero-delay timed self-loop (`accept after 0 [s]` back to
> its own source) re-arms on every entry and starves any other time trigger on
> the same state; it never quiesces, so it must only be run under a
> bounded `execute(max_steps=...)`.

### 3.5 **WiP** `accept at <instant>` → one-shot delayed event, armed conditionally

*Corpus: none yet (will be added when this lands)*

*Spec: SysML 7.17.8 (time triggers); KerML 9.2.14 (`TriggerAt`)*

An absolute time trigger rides the same machinery as 3.4; only the arming
differs. The deadline is absolute, so the delay is computed at arming time:
`on entry` evaluates the instant against the interpreter clock (whose epoch is
0, a documented convention: SysML leaves the clock unbound) and schedules the
tick only when the result is not already in the past.

```sysml
state def MachineAt {
    attribute startInstant : TimeInstantValue default 8 [s];
    entry;
        then idle;
    state idle;
    state running;

    transition first idle accept at startInstant then running;
}
```

```yaml
statechart:
  name: MachineAt
  preamble: |
    startInstant = 8.0
    _n_idle = 0
  root state:
    initial: idle
    name: MachineAt
    states:
    - name: idle
      on entry: |
        _n_idle = _n_idle + 1
        _d_idle_t1 = (startInstant) - time
        if _d_idle_t1 >= 0:
            send("_tick_idle_t1", n=_n_idle, delay=_d_idle_t1)
      transitions:
      - {event: _tick_idle_t1, guard: event.n == _n_idle, target: running}
    - {name: running}
```

*Why the `>= 0` arming conditional:* KerML's time condition is a strict
equality, and on an advancing clock an instant already in the past never
satisfies it again: the literal reading of `at T` armed after `T` is **never
fires**. The conditional implements exactly that reading (without it, the
negative delay silently degrades into fire-at-next-step, the looser
"reaches" reading of the SysML prose). Choosing the literal reading is a
documented decision; the alternative is one `max(0, ...)` away if ever wanted.

> ⚠️ **Limitation:** SysML prose says the signal occurs when current time
> "reaches" the instant; KerML encodes strict equality. A discrete simulator
> cannot sample exact equality, so delivery is at the first macro step at or
> past the deadline; for a future instant the two readings agree there.

### 3.6 **WiP** `accept when <cond>` → armed flag + consumer pair

*Corpus: none yet (will be added when this lands)*

*Spec: SysML 7.17.8 (change triggers), 8.4.13.6 (`TriggerWhen`); KerML 9.2.13
(Observation: `ObserveChange`, `ChangeMonitor`)*

**The semantics being implemented**: a change trigger arms
**one observation per activation** of its source state. The signal is sent at
the first false-to-true crossing observed while the state is active, OR
**immediately if the condition is already true at arming**: that is the
spec's own parenthetical ("or sent immediately if the expression is true when
first evaluated"), matched by the stdlib wiring, so a change trigger is *not*
a pure edge. If the `if` guard is false at delivery, the signal is
**consumed**: nothing fires for the rest of that activation, even if the
condition falls and rises again. Re-entering the state arms a fresh
observation, so a still-true condition fires again, once, after every
re-entry. Arming happens at state entry (the spec leaves the instant unpinned;
entry is the documented tool choice).

**The mapping.** No events needed. Per trigger, the `preamble` initializes an
**armed flag**, the source's `on entry` re-arms it, and the trigger becomes a
transition **pair** sharing that flag:

- the **real** transition: guard `armed and (cond) and (g)`, the user's
  target and effect, higher priority;
- a synthetic **consumer**: an internal transition (no `target`, so firing it
  exits and enters nothing) with guard `armed and (cond)` and action
  `armed = False`, lower priority.

While `g` holds at the delivery instant, the higher-priority real transition
wins and fires; while `g` is false, the consumer fires instead and disarms:
consumption, expressed as chart structure. For a bare `accept when` with no
`if` guard the consumer is not emitted (there is no guard to reject delivery),
leaving just the real transition.

```sysml
state def MachineWhen {
    attribute cold : Boolean := false;
    attribute enabled : Boolean := true;
    entry;
        then idle;
    state idle;
    state running;

    transition first idle accept when cold if enabled then running;
}
```

```yaml
statechart:
  name: MachineWhen
  preamble: |
    cold = False
    enabled = True
    _w_idle_t1 = False
  root state:
    initial: idle
    name: MachineWhen
    states:
    - name: idle
      on entry: _w_idle_t1 = True
      transitions:
      - guard: _w_idle_t1 and (cold) and (enabled)
        priority: 2
        target: running
      - guard: _w_idle_t1 and (cold)
        priority: 1
        action: _w_idle_t1 = False
    - {name: running}
```

*Why the disarm lives in an action, not in the guard:* the one-transition
alternative would make the guard itself remember and consume (mutate the flag
while being evaluated). But sismic evaluates guards while **selecting** which
transitions fire, and a selected transition can still be discarded when
conflicts are resolved (two parallel regions can co-select conflicting
transitions). A side effect in the guard runs even on a discarded step: the
flag would be consumed with the source still active and nothing fired, losing
the signal by scheduling accident. A transition **action** runs only when the
step **commits**, so consumption can never happen by accident.

*Why the consumer has no `target`:* consuming must be invisible. A targeted
transition would exit and re-enter `idle`, re-running `on entry`: user entry
actions would execute again and the flag would be re-armed, undoing the
consumption. An internal transition fires its action while staying put.

*Why priorities:* the generator assigns descending declaration-order
priorities to every eventless transition sharing a source (higher number wins
in sismic). That keeps each real transition above its consumer, makes several
`when` triggers on one source deterministic instead of a
`NonDeterminismError`, and pins a tie rule for free: a `when` and an `after`
due at the same instant resolve **when-first**, because eventless transitions
are selected before event delivery (the ordering in "The statechart at a
glance").

> ⚠️ **Limitation (sampling):** the condition is observed once per macro step.
> A pulse that rises and falls entirely between two macro steps is missed;
> rises must persist until the next step. The spec pins no sampling instant,
> so this cadence is a documented tool choice.

> ⚠️ **Boundary:** a `when` self-loop whose effect cannot falsify its own
> condition never quiesces: the literal SysML model re-fires once per
> activation, indefinitely. (The spec does **not** say "fires once": the only
> "once" near 7.17.8 is a comment inside a transition-free example.) The
> generator rejects the shape at build time for the same reason it rejects the
> bare eventless self-loop: the macro-step engine cannot terminate on it. That
> is an engine limitation, never a claim that the model is invalid SysML.

______________________________________________________________________

## 4. Actions & effects

In SysML a state can carry three actions, `entry`, `do`, and `exit`, and a
transition can carry an effect. All of them become Python statements
(assignments and `send` calls, newline-joined). On the sismic side there are
only **two** action slots per state, `on entry` and `on exit`, and no slot for
an ongoing activity: SysML's `entry` and `do` both land in sismic's `on entry`
(the `do` as a run-once action, 4.3), `exit` lands in `on exit`, and a
transition effect lands in the sismic transition's `action`. An assignment
emits as `name = <expr>` (`:=` to `=`), its right-hand side following the same
expression rules as guards (Section 3.3). An action body may contain **only**
assignments and `send`s: any other action kind in the body (an `accept`, a
control node, ...) is rejected fail-loud.

### 4.1 `entry action` / `entry assign` → `on entry`

*Corpus: [`sm04-assignment`](../models/sm-examples/sm04-assignment/sm04.sysml)*

*Spec: SysML 7.18.2 (entry actions), 7.17.9 (assignment action usages)*

In SysML, an `entry action` is behavior a state runs when it is entered;
`entry assign x := e;` is the shorthand for a single assignment. Both map to the
state's `on entry`.

```sysml
state def MachineEntryShorthand {
    attribute counter : Integer := 0;
    entry; then idle;
    state idle {
        entry assign counter := counter + 1;
    }
    state running;
    transition first idle then running;
}
```

```yaml
statechart:
  name: MachineEntryShorthand
  preamble: counter = 0
  root state:
    initial: idle
    name: MachineEntryShorthand
    states:
    - name: idle
      on entry: counter = counter + 1
      transitions:
      - {target: running}
    - {name: running}
```

> ⚠️ **Limitation:** only the inline forms are translated. The referencing form
> (`entry helper;`, performing an action declared elsewhere, valid SysML) is
> **silently dropped**: the state builds with no `on entry`, and the helper's
> effect never runs. The same holds for `exit`. (A `do` that references another
> action is rejected fail-loud instead, 4.3.) Planned support: translate the
> referenced action when standalone actions are supported.

### 4.2 `exit action` / `exit assign` → `on exit`

*Corpus: [`sm04-assignment`](../models/sm-examples/sm04-assignment/sm04.sysml)*

*Spec: SysML 7.18.2 (exit actions), 7.17.9 (assignment action usages)*

An `exit action` (or `exit assign`) runs when the state is left, and maps the
same way to the state's `on exit`:

```sysml
state def MachineExitShorthand {
    attribute counter : Integer := 1;
    entry; then idle;
    state idle {
        exit assign counter := counter - 1;
    }
    state running;
    transition first idle then running;
}
```

```yaml
statechart:
  name: MachineExitShorthand
  preamble: counter = 1
  root state:
    initial: idle
    name: MachineExitShorthand
    states:
    - name: idle
      on exit: counter = counter - 1
      transitions:
      - {target: running}
    - {name: running}
```

### 4.3 `do action` → `on entry` (run once)

*Corpus: [`sm12-do-action`](../models/sm-examples/sm12-do-action/sm12.sysml)*

*Spec: SysML 7.18.1 (do action semantics), 7.18.2 (do actions)*

In SysML, a `do action` is behavior that runs *while* a state is active (an
ongoing activity). sismic states have no such slot, so the generator maps a `do`
body to a **run-once** action at state entry.

```sysml
state def MachineDoShorthand {
    attribute progress : Integer := 0;
    entry; then working;
    state working {
        do assign progress := progress + 1;
    }
    state finished;
    transition first working then finished;
}
```

```yaml
statechart:
  name: MachineDoShorthand
  preamble: progress = 0
  root state:
    initial: working
    name: MachineDoShorthand
    states:
    - name: working
      on entry: progress = progress + 1
      transitions:
      - {target: finished}
    - {name: finished}
```

*Why:* a sismic state has only `on entry`/`on exit`, no activity slot. Run-once
at entry is faithful for a body of assignments and sends: the activity would
run to completion anyway, and it applies uniformly to leaf, composite, root,
and region states. When a state has both `entry` and `do`, the emitted code is
entry first, then do, regardless of how they are declared: SysML starts the do
only after the entry action completes:

```yaml
on entry: "log = 1\nlog = log + 10"   # entry assign, then do action
```

> ⚠️ **Boundary:** only an inline `assign`/`send` body is supported **today**.
> SysML allows a `do` body to be a genuinely ongoing activity: it can contain
> an `accept` (the activity pauses until a signal arrives, while the state
> stays active), a loop (the activity repeats for as long as the state is
> active), or a reference to another action (a typed perform, or the
> `do other;` shorthand). None of those fit a run-once `on entry` string: a
> one-shot cannot wait, repeat, or perform another action, and emitting it
> anyway would silently change the model's behavior. The generator therefore
> **rejects** these shapes fail-loud for now. Support is planned: an ongoing
> activity needs a different encoding (expressed as chart structure, e.g.
> internal transitions reacting to events, rather than a bigger entry string).

### 4.4 transition effect (`do action ... then`) → `{action: ...}`

*Corpus: [`sm06-transition-effect`](../models/sm-examples/sm06-transition-effect/sm06.sysml)*

*Spec: SysML 7.18.3 (transition effect), 7.17.9 (assignment action usages);
KerML 9.2.10.1 (effect ordering)*

In SysML, a transition's **effect** is behavior performed when the transition
fires, written with `do` between the trigger/guard and the `then` target. It maps
to the sismic transition's `action`. The block form (`do action { assign ... }`) and
the shorthand (`do assign x := e`, or `do send ...`, 4.5) emit identically.

```sysml
state def MachineEffect {
    attribute counter : Integer := 0;
    entry; then idle;
    state idle;
    state armed;
    state running;
    transition first idle do action { assign counter := counter + 1; } then armed;
    transition first armed then running;
}
```

```yaml
statechart:
  name: MachineEffect
  preamble: counter = 0
  root state:
    initial: idle
    name: MachineEffect
    states:
    - name: idle
      transitions:
      - {action: counter = counter + 1, target: armed}
    - name: armed
      transitions:
      - {target: running}
    - {name: running}
```

*Why:* within one transition step the order is `source on exit`, then the
transition `action`, then `target on entry` (the `sm07-firing-order` example
exercises exactly this order).

> ⚠️ **Limitation:** a **referencing effect** (`do helper`, performing an action
> declared elsewhere) is **silently dropped**, exactly as for `entry`/`exit`
> (4.1): the transition builds with no `action` and the helper never runs. Same
> planned support as 4.1.

### 4.5 `send new Sig(args) [via port]` → `send("Sig", kwargs)`

*Corpus: [`sm11-send-effect`](../models/sm-examples/sm11-send-effect/sm11.sysml)*

*Spec: SysML 7.17.7 (send action usages); KerML 8.3.4.8.7 (instantiation
argument binding)*

In SysML, `send new Sig(args)` emits a signal. As a transition effect it becomes
a sismic `send(...)` call in the transition's `action`; in a state's
`entry`/`exit`/`do` body the same call lands in `on entry`/`on exit`. Here the
machine that sends then accepts its own event, modeling a **single-machine
self-send**.

```sysml
state def MachinePayload {
    attribute current : Integer := 7;
    port commPort;
    entry; then idle;
    state idle;
    state armed;
    state fired;
    transition first idle do send new Reading(current) via commPort then armed;
    transition first armed accept Reading via commPort then fired;
}
```

```yaml
statechart:
  name: MachinePayload
  preamble: current = 7
  root state:
    initial: idle
    name: MachinePayload
    states:
    - name: idle
      transitions:
      - {action: 'send("Reading", value=current)', target: armed}
    - name: armed
      transitions:
      - {event: Reading, target: fired}
    - {name: fired}
```

*Why:* a positional payload argument binds to the item's attribute name as a
keyword (`Reading { attribute value }` gives `value=current`); a payload-less
send is just `send("Ping")`. The keyword genuinely travels with the event
(sismic itself would expose it to guards as `event.value`), but no construct we
translate can read it yet: the `accept` side's payload binding is not supported
(limitation in 3.2).

> ⚠️ **Limitation:** the `via commPort` receiver is **dropped**, as on the
> `accept` side (3.2): a port only matters for cross-machine routing, when
> several state machines are simulated together and the transfer must reach a
> specific one. A single statechart has nothing to route between.
