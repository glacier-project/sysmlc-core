# Design dialogue — positioning statix

> **Migrated into sysmlc (2026-07).** This is a historical record; statix is now
> a sysmlc backend consuming the shared neutral facts (no standalone JSON IR).
> See [architecture.md](architecture.md) for the current design.

> A verbatim record of the strategy conversation that shaped statix's direction
> (2026-07). Questions are the maintainer's; answers are the assistant's,
> reproduced as given. The synthesized deep-dive that came out of this is in
> [positioning.md](positioning.md).

---

## Q1 — "Check what boost::sml has more than us and how we can extend ours (probably just write a readme for now)."

**A.** Fetched and analyzed `boost/sml.hpp`, then wrote
`docs/comparison_boost_sml.md` rather than implementing anything.

Key takeaway: boost::sml and statix optimize for opposite things. `sml` is a
compile-time **C++ template-metaprogramming** library; a big chunk of its surface
— exceptions, `pool`/`try_get` dependency injection, `thread_safe<lock>`, dynamic
`std::queue` deferral, inline generic-lambda actions — relies on exactly the
mechanisms a Power-of-10 C99 runtime must avoid. So those aren't gaps to close;
they're **deliberate non-goals** with statix-native equivalents (`sc_status_t`
returns instead of exceptions, a single `user_data` pointer instead of DI pools).

What's worth chasing is **statechart expressiveness**, grouped as:

- **Near-term, constraint-respecting wins:** wildcard source state (`_` →
  `SC_STATE_ANY`), terminal states + `is_terminated()`, anonymous/completion
  transitions with a bounded run-to-completion loop (with a generated
  `SC_MAX_RTC_STEPS` cap so Rule 2 holds), optional link-time trace hooks (no
  function pointers).
- **Already on the roadmap:** entry/exit actions, composite/hierarchical states,
  parallel regions, shallow history.
- **Generator-side polish:** composable guards (`&&`/`||`/`!`) and multi-action
  transitions synthesized into single generated ids; typed event payloads.

Closing point: statix's authoring model (external IR → auditable generated C99)
is itself a safety feature — a reviewer/analyzer sees exactly what runs on the
target.

---

## Q2 — "How useful would it be if we reimplement here with my idea of how this library should work, instead of the boost approach? Is it worth going down this path? Be honest."

**A.** You're not actually choosing between "your way" and "boost's way."
boost::sml is an **inline C++ template-metaprogramming library**; statix is a
**code generator that emits static C**. Those are different product categories.
You diverged from boost the moment you chose IR + codegen + C99. The one version
of "do it my way" that is *not* worth it is trying to recreate boost's inline-DSL
ergonomics in C — you can't get there without macro-hell, and codegen is already
the correct answer to that.

boost is also the wrong benchmark. The real comparison set is the codegen tools:
**itemis CREATE / YAKINDU**, **StateSmith**, **MathWorks Stateflow**, **IAR
visualSTATE**, older **Ragel**. "Generates C from a state model" is a solved,
crowded space; boost being C++-only makes statix look more novel than it is
against those.

Is it worth it? Depends on one thing: **can the target run C++?**

- **If C-only / cert-driven** (DO-178C / ISO 26262 / IEC 61508 shops that ban
  template metaprogramming, or freestanding C toolchains) — boost::sml is simply
  unavailable to you, and a Power-of-10, no-dynamic-memory, no-function-pointer,
  auditable-generated-C statechart tool has a **real, defensible niche**. Worth
  building; the alternatives are expensive commercial tools.
- **If C++ is fine** — reimplementing to reach boost/itemis parity is a
  multi-year effort you'll probably lose, unless you have a specific
  differentiator.

Honest cost/risk: "designed to follow Power of 10" is cheap; *delivering the
safety story* (requirements traceability, MC/DC coverage of generated code, a
qualified generator, tool-confidence documentation) is 80% of the real work and
100% of why anyone picks you over hand-writing a switch. Without that investment,
statix is "a nice codegen toy."

Prior: **worth it if and only if the target is C-only / cert-driven** — the one
lane where you're not rebuilding something that already exists. (Ended by asking:
what's the target, what's your actual idea, and what's the goal — product vs
reference implementation?)

---

## Q3 — "My idea is to hook the SysML v2 parser my colleagues and I use to the other backends. We have backends that generate Sismic code (quake) and Lingua Franca modal reactors (rosetta); this one goes directly to C, ready for microcontroller — like TensorFlow Lite makes an ML model a pure header for an Arduino."

**A.** That changes everything — clear "yes," and more interesting than "another
statechart library."

**Verdict — the success criterion is not "features."** You're building the
**deployment leg of a multi-backend SysML v2 toolchain**: quake → Sismic
(*simulate/verify*), rosetta → Lingua Franca (*real-time reactive execution*),
statix → C (*flash it on the MCU*). That makes the boost comparison irrelevant,
and the TFLite-Micro analogy is exactly the right North Star: a small, static,
self-contained C artifact produced from a high-level model. No one in the matrix
does that leg, so statix isn't redundant with quake or the front-end.

**What the TFLite-Micro analogy commits you to.** Its trick is one tiny audited
runtime + the model as a `const` data blob + a user-provided static arena, zero
malloc. statix sits between two options: **(A) interpreter + data tables** (one
generic runtime, shared audited core — roughly where you are) and **(B) full
per-model codegen** (bespoke goto-free switch per model — StateSmith/itemis). For
the "drop-in `.h` on an Arduino" ergonomic, add an **amalgamation / single-header
build** early: it's cheap and it's 90% of the *perception* of "TFLite Micro for
statecharts."

**The real hard problem — semantic consistency across backends.** Sismic
(SCXML/UML run-to-completion, microstep/macrostep) and Lingua Franca (reactor
model, logical time, deterministic concurrency, modes) have very different
execution semantics. If the same model must *mean the same thing* everywhere,
statix's semantics must be **pinned precisely** — and the current "first matching
row wins, one region, no RTC" is under-specified relative to Sismic. The killer
feature is **cross-backend conformance testing**: same model + same event trace
into Sismic and into statix's C, assert corresponding traces. That's what turns
"three code generators" into "one trustworthy toolchain."

**The honest risk — your overlap is rosetta, not boost.** Lingua Franca already
compiles to C and has embedded ambitions. The sharp question: why does statix
exist next to `rosetta → LF → C`? Defensible answer = footprint + execution
model. LF ships a **reactor runtime** (scheduler, logical-time machinery,
threading in general); statix should be a **synchronous, no-scheduler,
no-dynamic-memory statechart dispatcher** small enough for a tiny Cortex-M0. If
that footprint delta is real, statix is justified; if LF-C already fits your
smallest target, statix risks being "the poor man's LF backend." That boundary
must be stateable in one sentence, about *size/determinism/bare-metal*, not
features.

**Three things needed to design it well:**

1. Is there already a **shared IR** quake and rosetta consume, or does each
   backend re-parse SysML v2? statix currently has its own JSON IR; if an
   ecosystem IR exists, statix should consume *that* (its `ir.py` becomes a thin
   adapter). Most important structural decision.
2. **Which semantics is the source of truth?** Almost certainly Sismic/SCXML
   (since quake is the verification backend). If so, target that run-to-completion
   semantics precisely — which reshapes the roadmap (RTC and entry/exit ordering
   matter more than wildcard transitions).
3. **The footprint boundary vs LF:** the smallest target statix must hit that
   rosetta/LF-C can't. That's the one-sentence reason to exist.

Suggested first build: the **conformance-testing harness** that ties the backends
together — it's the piece that makes the ecosystem credible.
