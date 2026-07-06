# statix — positioning & strategy

> **Migrated into sysmlc (2026-07).** statix is now a first-class sysmlc backend
> (`sysmlc/backends/statix`) that consumes sysmlc's neutral state-machine facts
> directly. The standalone JSON IR / `scgen` CLI referenced in places below is
> historical context — see [architecture.md](architecture.md) and
> [statix-mapping.md](../statix-mapping.md) for the current design. The strategy
> and "why" it records still stand.

> Status: strategy document, not a spec. It records *where statix should sit*,
> *why it should exist*, and *what to build in what order*. It goes deeper than
> the [design dialogue](design-dialogue.md) it grew out of. Where it makes
> recommendations, it says so; where a decision is still open, it says that too.

______________________________________________________________________

## 1. One-paragraph positioning

**statix is the bare-metal deployment backend of a SysML v2 statechart
toolchain.** A shared SysML v2 front-end feeds several backends; statix is the
one that compiles a *verified* statechart model into **static, self-contained,
Power-of-10-clean C** that is ready to flash onto a microcontroller — with no
dynamic memory, no function pointers, no RTOS dependency, and an artifact a
reviewer or static analyzer can read directly.

The value is not "another state-machine library." The value is *being one leg of
a model → verify → deploy pipeline where the same model provably behaves the same
way across backends.*

## 2. The ecosystem statix lives in

```
                         ┌─────────────────────────────┐
                         │   SysML v2 statechart model │   (authored / MBSE)
                         └───────────────┬─────────────┘
                                         │ parse
                         ┌───────────────▼─────────────┐
                         │   Shared front-end / IR     │   ← the contract
                         └───┬───────────┬───────────┬─┘
                             │           │           │
              ┌──────────────▼──┐  ┌─────▼───────┐  ┌▼────────────────┐
              │ quake           │  │ rosetta     │  │ statix          │
              │ → Sismic (Py)   │  │ → Lingua    │  │ → C (this repo) │
              │                 │  │   Franca    │  │                 │
              │ SIMULATE /      │  │ modal       │  │ DEPLOY on a     │
              │ VERIFY          │  │ reactors    │  │ microcontroller │
              │                 │  │ REAL-TIME / │  │                 │
              │                 │  │ REACTIVE    │  │                 │
              └─────────────────┘  └─────────────┘  └─────────────────┘
```

Each backend answers a different question about the *same* model:

- **quake** (Target: Sismic / Python)
  - Question it answers: "Is the design correct? What does it do?"
  - Model of computation: SCXML / UML statecharts, run-to-completion.
- **rosetta** (Target: Lingua Franca)
  - Question it answers: "How does it behave in real time, concurrently?"
  - Model of computation: Reactors: logical time, deterministic concurrency.
- **statix** (Target: C on MCU)
  - Question it answers: "How do we ship it on tiny hardware?"
  - Model of computation: Synchronous statechart dispatch, static memory.

statix's job is **fidelity + frugality**: reproduce the verified behavior, on the
smallest possible target, with the strongest possible auditability.

## 3. The one-sentence reason to exist (the rosetta boundary)

The single most important thing to be able to say. Your overlap risk is **not**
boost::sml or StateSmith — it's your own `rosetta → Lingua Franca → C` path, since
LF already emits C and targets embedded platforms. The defensible boundary is
**execution model and footprint**, not features:

> *statix targets synchronous, single-threaded, no-scheduler, statically-allocated
> statecharts small enough for a kilobyte-class MCU; Lingua Franca targets timed,
> concurrent, deterministic reactor systems and carries a scheduler/runtime to do
> so.*

Concretely, the litmus test: **is there a target where LF-C does not comfortably
fit, but statix does?** If yes (an 8-bit AVR / Cortex-M0+ with a few KB RAM, no
RTOS, hard determinism, cert constraints), statix is justified and rosetta is
complementary. If no, statix is redundant and should be folded into rosetta. This
is **open decision #3** below — it must be answered honestly before heavy
investment.

## 4. The real competitive landscape (be honest)

boost::sml is a red herring. The tools that actually occupy statix's niche:

- **StateSmith**
  - Kind: codegen, open (MIT)
  - Source model: PlantUML / draw.io / YAML
  - Memory / dispatch: static, single switch fn
  - Notes: Closest open peer *in spirit*. Mature-ish, active.
- **itemis CREATE** (YAKINDU SCT)
  - Kind: modeling tool + codegen, commercial + community
  - Source model: own statechart notation
  - Memory / dispatch: static, generated C/C++/Java
  - Notes: SCXML-ish semantics, simulation, established in industry.
- **IAR visualSTATE**
  - Kind: commercial
  - Source model: own notation
  - Memory / dispatch: generated C + formal checks
  - Notes: Automotive/industrial; verification story.
- **Stateflow + Embedded Coder**
  - Kind: commercial (MathWorks)
  - Source model: Simulink/Stateflow
  - Memory / dispatch: generated C
  - Notes: Dominant in automotive/aero; huge, heavy.
- **QP/QM** (Quantum Leaps)
  - Kind: framework + free modeling tool
  - Source model: QM diagrams
  - Memory / dispatch: **function-pointer** state handlers, active objects
  - Notes: Very embedded-focused; dual GPL/commercial. *Uses function pointers — which Power of 10 forbids.*
- **Zephyr SMF**
  - Kind: C framework (no codegen)
  - Source model: hand-written tables
  - Memory / dispatch: static
  - Notes: Part of Zephyr RTOS; not model-driven.
- **Ragel**
  - Kind: state machine compiler
  - Source model: regex-like
  - Memory / dispatch: generated C
  - Notes: Protocol/lexer FSMs, not UML statecharts.
- **statix**
  - Kind: codegen, open
  - Source model: **SysML v2** (via shared IR)
  - Memory / dispatch: **static, no function pointers, Power of 10**
  - Notes: Pipeline member + strict safety posture.

Honest reading of this table:

- **Against StateSmith specifically**, statix has *no* automatic advantage. If you
  strip away the ecosystem and the strictness, statix ≈ "StateSmith with fewer
  features." Your differentiation must be real and defended:
  1. **SysML v2 front-end + multi-backend equivalence** (StateSmith is a
     standalone tool; statix is part of a verified pipeline).
  1. **Power-of-10 / MISRA-grade strictness** as a first-class, tested property
     (no function pointers, no heap, bounded everything) — most competitors,
     notably QP, *do* use function pointers.
  1. **Cross-backend conformance evidence** (§6) — nobody else can offer "the C
     provably matches the verified Sismic model."
- **Against QP/QM**, statix's honest edge is the safety posture (QP's classic
  design is function-pointer-based) and openness; QP's edge is maturity, active
  objects, and a large install base. Respect it.

If you cannot deliver #1–#3, the honest conclusion is "use StateSmith." So those
three are not nice-to-haves; they are the reason to exist.

## 5. The core technical problem: semantic consistency across backends

This is the intellectual heart of the whole project and the thing most likely to
be underestimated. Three backends, three **models of computation (MoC)**:

- **Sismic** — SCXML/UML statechart semantics: an event triggers a
  *run-to-completion (RTC)* step; within a step, microsteps fire enabled
  transitions until stable; entry/exit actions run in a defined order; internal
  event queues; conflict resolution by priority/scope.
- **Lingua Franca** — reactor semantics: reactions execute at *logical time*
  tags, deterministic concurrency, modes as modal models. Time is a first-class,
  well-defined concept; concurrency is deterministic by construction.
- **statix** — *currently* a single-region, first-match, one-transition-per-call
  dispatcher with **no RTC, no entry/exit, no microsteps.** This is *weaker and
  under-specified* relative to Sismic.

The danger: the "same" model silently means three different things. To be a
credible toolchain you need:

1. **A written reference semantics** for the SysML v2 statechart *subset* you
   support — ideally expressed once, at the IR level, and cited by all backends.
   Pragmatically, **adopt Sismic/SCXML RTC semantics as the oracle**, because
   quake is your verification backend (open decision #2).
1. **statix's runtime redefined to implement that semantics precisely** for the
   supported subset: RTC step, deterministic transition selection, entry/exit
   ordering, internal-event handling. This is a bigger deal than any single
   "feature" on the boost-comparison list.
1. **A defined correspondence with LF.** Statechart RTC and reactor logical-time
   execution do not map trivially (especially *timed* behavior). Decide the
   agreed subset where all three coincide (likely: untimed, event-driven,
   deterministic) and explicitly mark where they diverge (timers, concurrency).
1. **Trace equivalence as the definition of "correct."** Two backends "agree" iff
   for the same input event sequence they produce corresponding state/output
   traces (modulo a documented mapping). This is testable — see §6.

Practical guidance: **do not chase parallel regions / history / timers first.**
Chase *precise flat + hierarchical RTC semantics that match Sismic*, because
that's what makes the conformance claim true. Expressiveness without a pinned
semantics is worse than useless here — it manufactures disagreement between
backends.

## 6. The moat: cross-backend conformance & V&V

This is the differentiator no off-the-shelf tool gives you, and the reason the
three-backend architecture is more than the sum of its parts.

**Conformance harness (build this early — arguably first):**

```
        model.sysml ──► shared IR ──┬──► quake  ──► Sismic run  ──► trace_S
                                     └──► statix ──► C build+run ──► trace_C

        for each test in a corpus of (model, event_sequence):
            assert normalize(trace_C) ≡ normalize(trace_S)
```

- Sismic is an excellent **oracle**: it can execute a model in Python and emit a
  state/event trace. statix compiles the same model to C, runs the same event
  sequence on the host, emits its trace. A small driver diffs them.
- Start with the flat corpus (including the `simple_toggle`), grow it as
  hierarchy lands. Every new semantic feature ships with conformance tests, not
  just unit tests.
- Bonus: the same harness can compare **statix vs rosetta/LF** on the untimed
  subset, closing the triangle.

**V&V / certification posture (the expensive-but-defining part):**

- **Traceability:** carry model-element identifiers through the IR into the
  generated C (e.g. a comment/table mapping each transition row back to its SysML
  element id). This is gold for reviews and for any future DO-178C / ISO 26262
  argument.
- **Structural coverage:** the generated C is plain and branch-simple by design;
  measure MC/DC on it. "Our generated code is 100% MC/DC covered by the
  conformance corpus" is a strong, checkable claim.
- **Tool-qualification framing:** even if you never formally qualify the
  generator, *designing as if you might* (DO-330 tool qualification, ISO 26262
  tool confidence level) forces the right discipline: deterministic output,
  validated input, documented semantics, versioned IR. This is exactly what the
  current deterministic-emitter + "generated matches committed" test already
  gestures at — lean into it.

The moat sentence: **"statix emits static, function-pointer-free C whose behavior
is conformance-tested against a verified Sismic model, with every line traceable
to a SysML v2 element."** No competitor in §4 can say all of that.

## 7. Architecture: how the C should be shaped

Three viable shapes; statix is currently a hybrid of the first two. Choose
deliberately.

- **(A) Interpreter + data tables** (one generic `sc_runtime` + `const` tables)
  - What it is: one generic runtime core + constant tables (current design).
  - Pros: one audited core; tiny per-model data; many models cheap; matches TFLite-Micro.
  - Cons: a (small) generic interpreter loop.
- **(B) Per-model full codegen** (bespoke `switch` machine per model)
  - What it is: emit a bespoke goto-free `switch` machine per model; no generic core.
  - Pros: nothing to interpret; fully inlined; each artifact self-contained.
  - Cons: more generated code; less shared audited core; harder cross-model reuse.
- **(C) Amalgamation single-header** (collapsed into one file)
  - What it is: ship (A) or (B) collapsed into one `.h`/`.c` (or one header).
  - Pros: *the* "drop-on-Arduino" ergonomic; trivial integration.
  - Cons: build-time concatenation step; care with include-once.

**Recommendation:**

- Keep **(A)** as the substrate (it *is* the TFLite-Micro shape and it keeps the
  audited surface small), but make the generated per-model dispatch as flat and
  branch-simple as **(B)** so coverage/analysis is easy. You already do this for
  guards/actions via generated switches.
- Add **(C)** as a *packaging* option early — an amalgamation build that emits
  `my_machine.h` (+ optional `.c`) bundling the runtime and the generated tables.
  This is cheap, and it's most of the *perceived* "TFLite Micro for statecharts"
  value.
- Keep the **binding discipline** you already have: guards/actions resolved at
  **link time** by integer id + generated `switch`, never function pointers. This
  is a genuine differentiator vs QP and others — protect it.
- **Memory model:** follow TFLite Micro's "arena" idea conceptually — *all* state
  (runtime instance, event-queue storage, any future history slots) lives in
  caller-provided storage sized by generated `#define`s. No hidden statics, no
  allocation, ever. This is already the direction; make it a hard invariant with
  a test that greps the build for `malloc`/`calloc`/`realloc`/`free`.

## 8. The IR contract (probably the highest-leverage decision)

statix currently defines its **own** `schema/statechart_ir.schema.json`. In a
multi-backend world that is likely the wrong long-term shape.

- **If a shared ecosystem IR already exists** (the front-end produces one AST/IR
  that quake and rosetta consume): statix should consume *that*. Its `scgen.ir`
  becomes a **thin adapter** from the shared IR to statix's emitter, and the
  standalone JSON schema is demoted to "a convenient serialization for standalone
  use / tests." **Do not maintain a second, divergent notion of a statechart.**
- **If there is no shared IR yet** (each backend re-parses SysML v2): this is an
  opportunity — a small, versioned, well-documented **canonical statechart IR**
  could become the shared contract, with statix's current schema as the seed.
  That's a bigger political/organizational move (it's now *the team's* IR, not
  statix's), but it's the right architecture.

Either way, the IR should carry, from day one:

- **Provenance / traceability metadata** (SysML element ids) for §6.
- **An explicit semantics tag / profile** (e.g. "SCXML-RTC-untimed-v1") so a
  model declares which agreed subset it targets and backends can refuse what they
  can't honor — the same instinct as the current validator rejecting unsupported
  keys.
- **A schema version.** Cert and multi-backend both need stable, versioned
  contracts.

This is **open decision #1** and it gates almost everything else.

## 9. Phased roadmap

Sequenced so that *credibility* (conformance) comes before *expressiveness*.

- **Phase 0 — Contracts.** Decide the shared-IR question (§8). Write the
  reference-semantics note (§5) naming Sismic/SCXML-RTC as the oracle and the
  agreed untimed subset. Add the `no-dynamic-memory` grep test. *Deliverable: two
  short docs + one CI check. No new runtime features.*
- **Phase 1 — Flat, but correct + conformant.** Redefine the flat runtime to a
  precise RTC step matching Sismic for the flat subset. Build the **conformance
  harness** (statix-C vs Sismic) and a starter corpus. Add traceability comments
  to generated C. *Deliverable: "same trace as Sismic" for flat models, in CI.*
- **Phase 2 — Hierarchy (the real UML core).** Composite states, entry/exit
  actions with correct ordering, internal vs external transitions, bounded
  run-to-completion. Extend the corpus. This is where statix becomes a *real*
  statechart tool. (Depth bound = generated constant → Rule 2 preserved.)
- **Phase 3 — Deployment ergonomics + proof of frugality.** Amalgamation
  single-header build (§7C). **Footprint benchmarks vs LF-C** on a real small
  target — this produces the §3 one-sentence boundary as *data*, not assertion.
- **Phase 4 — Advanced statechart features.** Parallel regions, shallow history,
  timers (as bounded, statically-configured event sources). Each with conformance
  tests and a documented LF correspondence (or an explicit "diverges here").
- **Cross-cutting, always:** every feature ships with conformance + coverage;
  IR stays versioned; docs stay honest about what's supported.

The near-term boost-comparison wins (wildcard source, terminal states, trace
hooks) are still worthwhile, but they slot into Phases 1–2 *underneath* the
semantics work — they are not the headline.

## 10. Honest risks & failure modes

- **Redundancy with rosetta/LF** (§3). If the footprint boundary isn't real,
  statix is the poor man's LF backend. *Mitigation: answer decision #3 with data
  in Phase 3; be willing to kill or merge.*
- **Semantic drift between backends** (§5). The most likely *silent* failure: the
  three backends diverge and nobody notices until a model behaves differently in
  the field vs the simulator. *Mitigation: conformance harness as a gate, early.*
- **Scope creep toward feature parity** with itemis/StateSmith. Chasing features
  instead of the pipeline+conformance story turns statix into a weaker clone.
  *Mitigation: the moat sentence (§6) is the roadmap filter — if a feature
  doesn't strengthen pipeline/conformance/frugality/auditability, defer it.*
- **The cert story is expensive.** "Designed to follow Power of 10" is free;
  actual traceability + coverage + tool-confidence is real work. *Mitigation:
  bank it incrementally (traceability comments, coverage in CI) rather than as a
  big-bang effort.*
- **Shared-IR governance.** A team-owned IR needs an owner and a versioning
  discipline, or it rots into per-backend dialects. *Mitigation: make it explicit
  and versioned in Phase 0.*
- **Bus factor / academic cadence.** Research tooling often stalls after the
  paper. *Mitigation: keep statix independently useful (standalone JSON IR path)
  so it survives even if the ecosystem evolves.*

## 11. Open decisions (still unanswered — do these first)

1. **Shared IR?** Does an ecosystem IR that quake/rosetta consume already exist,
   and should statix adapt to it (recommended) or seed a canonical one? (§8)
1. **Semantic oracle?** Confirm Sismic/SCXML-RTC as the reference semantics and
   define the agreed untimed subset across all three backends. (§5)
1. **Footprint boundary vs LF-C?** The smallest target statix must hit that
   rosetta/LF-C can't — stated in one sentence, proven with data in Phase 3. (§3)

## 12. The research / publication angle

This is (also) an academic artifact, and the framing writes itself:

> *A model-based toolchain that compiles a single SysML v2 statechart into (i) an
> executable/verifiable Python model, (ii) a real-time deterministic reactor
> program, and (iii) static, function-pointer-free C for microcontroller
> deployment — with **cross-backend semantic conformance** established by trace
> equivalence.*

The publishable contribution is not "yet another C generator"; it is the
**one-model, multiple-MoC, conformance-checked** pipeline, with statix as the
evidence that a verified model reaches the smallest hardware unchanged in
meaning. That reframing is also the product strategy: the conformance harness and
the shared IR are simultaneously the research result and the engineering moat.

______________________________________________________________________

### The through-line

Everything above reduces to one discipline: **statix wins by being the
*trustworthy, tiny, auditable* leg of a *semantically-consistent* toolchain — not
by having the most features.** Pin the semantics, prove the conformance, keep the
C static and readable, and the positioning takes care of itself. Chase features
first and statix becomes a worse StateSmith.
