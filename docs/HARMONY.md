# HARMONY — agent coordination guardrails

> **HARMONY assumes a baseline of compliance and reasoning.** It is not a
> substitute for model capability. It makes well-trained, instruction-following
> models coordinate safely and efficiently. It does nothing for a model that
> won't read the spec. It provides no benefit to a model below the compliance
> floor.
> NEEDS REVIEW: tested/failed model list not yet filled.

> **Authorship:** the HARMONY coordination pattern (read-only/impl split,
> `earned-from:` provenance tags, verify-on-disk, per-run state, bounded tasks,
> append-only amendments) is the original work of **MelancholySky**
> (https://github.com/MelancholySky). Adopt it freely under MIT, but please
> credit the origin if you redistribute or build on it. This template is part
> of the `agent-guardrails-kit`.

> Living document. When a subagent discovers a NEW error, footgun, or
> failure mode while working in this project, it MUST report it back so this
> file can be updated. HARMONY is not static — it improves every time
> we learn something.

This file governs how we spawn and coordinate subagents (Warp
`run_agents`, implementation agents, and read-only QA agents) on the
**TF2autoswap** codebase.

> **MANDATORY — not optional.** These rules are binding on every agent that
> works in this repo, **including the orchestrator**. "Coordination guidance"
> means HARMONY is NOT a security boundary — it does NOT mean the rules are
> soft suggestions. A subagent that treats a rule as advisory has failed its
> task.

**Why the provenance tags matter.** Every rule below was produced by a
specific failure. The `earned-from:` annotations make the rule self-justifying
and rot-resistant.

**Scope.** HARMONY governs *agent coordination* for this repo. The *threat
model* and screening rationale live in `docs/SECURITY.md`; do not duplicate
them here.

## TL;DR (read this first if dropped in cold)

If you are a subagent and only read one block, read this:

1. **The operator's shell is fish 4.8 on CachyOS Linux.** Commands must be
   fish-compatible; avoid bash/zsh-only syntax. Prefer file creation tools
   over inline shell scripts (§1).
2. **Never call `wait_for_events`** — it cancelled twice during setup and
   hangs runs. Return your report as a message and stop (§3).
3. **QA = read-only, impl = may change but no commit** — probe scripts go
   in `/tmp`, never the project tree (§2, §2.1).
4. **Verify on disk** — don't trust your own self-report; the orchestrator
   re-checks (§4).
5. **Bounded, single-concern tasks** — one unit of work, independently
   testable (§7).
6. **One writer at a time** — never two agents mutating the same file in one
   turn; assign disjoint files or isolated worktrees (§7).
7. **A wedged child is cancelled + respawned fresh** — never resumed; on-disk
   state is authoritative after cancellation (§8).
8. **Do not edit project code directly if you are the orchestrator** —
   delegate all mutations to implementation agents (§10). The orchestrator's
   job is to coordinate, re-verify on disk, and hold the integration view.

## 1. Shell / tooling environment

The operator's shell is **fish 4.8 on CachyOS Linux**. Commands must be
fish-compatible:

- Use `for item in (command)` not `for item in $(command)`.
- Use `set var value` not `export var=value`.
- No bash/zsh heredocs — write files via the `create_file` tool.
- Pipe output through `psub` for process substitution, not `<()`.
- No `&&` / `||` chaining — run sequential commands as separate tool calls
  or use `; and` / `; or` fish syntax.

> **earned-from:** repeated shell-tool failures when agents used bash
> heredoc syntax under fish. Fish treats `<<` differently and $variable
> interpolation breaks in heredocs without quoting the delimiter.

## 2. QA agents are read-only; implementation agents may change

- **QA / Testing agents:** MUST NOT edit, create, delete, or move any
  project file, and MUST NOT `git commit`. They may only read and
  run read-only commands (`python3 -m pytest tests/ -q`), and throwaway
  probe scripts written to `/tmp` (importing the package by inserting the
  project root on `sys.path`) that do not modify project files.
  - **Probe scripts must be written to `/tmp` only** — never to any path
    under the project tree (including the repo root).
- **Implementation agents:** may change code + tests, but must NOT commit
  (commits are the operator's call).
- Both kinds verify with `python3 -m pytest tests/ -q` before reporting.

> **earned-from:** the read-only / mutate split keeps QA honest and prevents a
> verification agent from accidentally altering the artifact under test.

### 2.1 Empty model generations are transient, not success

The agent runtime may intermittently return **empty** model output. An empty
generation is a *transient failure*, never a valid result:

- If a generation returns empty, **retry with backoff** — do not silently
  proceed on the empty result.
- **Never** write a zero-byte / placeholder "success" file or report a task
  complete on an empty generation.
- This pairs with §4 (verify on disk): an empty generation that "succeeded"
  will fail the on-disk check, so surface it, don't paper over it.

> **earned-from:** flaky runtimes that strip message bodies have also emitted
> empty generations; treating either as success corrupts the run.

### 2.2 An unnameable failure is a classifier defect

Sibling to §2.1. Both are silent failure modes: §2.1 covers a failure that
returns as success, this covers a failure that returns as the wrong kind of
failure.

Any failure the system cannot name is a defect in the classifier, not an
acceptable outcome. When something fails, the classifier must be able to say what
class of failure it was. Where it cannot, that gap is reported as loudly as the
failure itself:

- Log the full exception type and traceback. Do not reduce an unrecognised
  failure to a summary that discards the type.
- Surface unclassified failures distinctly in run output and in run memory, so a
  gap in the classifier is visible as a gap rather than absorbed into an
  ordinary failure count.
- Have an explicit bucket for "I do not know", and prefer it over a confident
  guess. A wrong class sends the next attempt at the wrong fix, which costs a
  whole cycle and can break working code on the way.
- Never let the fallback be a plausible-looking class. A fallback that says
  "model failure" when the real cause was a connection error is worse than one
  that says nothing, because it is trusted.

A silent failure is worse than a loud one, because it is indistinguishable from
success until much later.

> **earned-from:** a timeout classifier keyed to one execution model's convention
> (a specific sentinel exit code) while another execution model raised a typed
> exception instead. Timeouts arriving by the second path fell through to a
> generic bucket and read as ordinary failures, so the gap survived undetected
> for the life of the feature.
>
> **invalid-if:** every execution model in use reports failure through the same
> mechanism, or the classifier is exercised against each one.

> **earned-from (measurement):** a reported measurement about system state is a
> hypothesis until verified on disk. A sweep reported a field as null in 99.96%
> of records; the aggregation was right and the conclusion was wrong, because the
> field was present and the claim needed correcting before it was repeated. Same
> rule as §4, one level up: a claim about the system is not evidence about the
> system.
>
> **invalid-if:** the measurement is re-derived against a specific named record
> rather than from aggregate counts alone.
## 3. NEVER call `wait_for_events`

The `wait_for_events` tool cancelled twice during the 2026-08-05 session
(setting up this project's structure). It appears to hang or collide with
the runtime's event delivery in this environment.

- **Do not call it.** When your task is complete, return your final report
  as a message and stop.
- The orchestrator checks for new messages via inbox notifications
  independently — you do not wait inside your own turn.
- If you are an implementation agent and the orchestrator asked you to
  "wait for QA," do NOT — just finish and report. The parent coordinates.

> **earned-from:** `wait_for_events` cancelled twice during 2026-08-05
> session, blocking the orchestrator from receiving child agent completion
> messages. The child agent's message arrived and was readable — the tool
> itself was the problem, not message delivery.

## 4. Verify on disk, don't trust self-reports alone

Because agent message bodies have intermittently come back EMPTY (the runtime
stripped them), the orchestrator re-verifies every change by grepping the
actual source and running tests directly. Treat an agent's "X tests pass" claim
as a hypothesis until confirmed on disk.

- After any change, the orchestrator runs `python3 -m pytest tests/ -q` and
  greps the diff. A change is "done" only when those are green AND the grep
  matches the claimed edit.
- For this project specifically, the orchestrator also checks: import chains
  still resolve (`python3 -c "import tf2_core, tf2_material, tf2_schema"`),
  and the `CHANGELOG.md` is still findable at the root.

> **earned-from:** empty agent message bodies made self-reports untrustworthy;
> the runtime stripped reports even when the work on disk was correct.

### 4.1 When disk cannot be trusted, two non-shared contexts cross-check

The inverse of §4. §4 says the filesystem is the oracle. This covers the case
where the filesystem is the thing that was destroyed.

Two agent contexts that **do not share context** are a valid independent
cross-check. The precondition is genuine independence: two agents reading the
same files, or one handed the other's summary, share a single point of failure
and the check is worthless.

- Use it when the normal oracle is unavailable or itself suspect: a tree deleted
  mid-run, a corrupted working copy, a state file written by the component under
  test.
- State which two contexts are being crossed and how they are known to be
  independent. Independence is the claim that makes the check mean anything.
- Treat the result as corroboration, not proof. Two independently wrong contexts
  agreeing is possible, and agreement between them does not establish that either
  is right.

This is a valid technique, not a guarantee.

> **earned-from:** an agent deleted a project directory with `rm -rf` in
> unsupervised mode, taking the git repository with the working tree. Recovery
> was cross-checked against a second agent that still held the project in
> context. It worked, but only because that second context happened to exist.
> The `rm -rf` itself is already denied by the command gate in `SECURITY.md`;
> what this rule covers is what to do once the oracle is gone.
>
> **invalid-if:** the project has an independent backup or a remote with a current
> copy, which is a stronger oracle than any agent's context.
### 4.2 A check that cannot fail is not a check

> **Tier tag:** «REPLACE: [PORTABLE] / [COMPENSATING] / [STANDARD]» — from your own
> run evidence, per the models named at the top of this file

A test asserting that a string appears in source text passes whether or not the
behaviour exists. `"field" in src` is a claim about a file, not about the system.
It stays green when the implementation is deleted, when the symbol is renamed,
and when a field is declared in the schema but never written.

Assert the behaviour instead. Run the thing and check what comes out.

- Source-text assertions verify that the code *mentions* something. Presence is
  not behaviour, and the gap between them is invisible while both are true.
- A test that passes before and after the implementation is removed was never
  testing it. Deleting or breaking the covered behaviour on purpose is the
  cheapest way to find out, and it finds out in seconds.
- This bites hardest on the checks guarding something invisible. A green suite is
  evidence that the suite passed, not that the guarded property holds. Where a
  property can be absent with no test noticing, the suite is reporting on itself.

A false green is worse than no test at all, because it is trusted. It is the same
shape as §2.1 and §2.2: a signal that reads as success and carries no
information.

> **earned-from:** two tests asserted that `duration_s` and `failure_class`
> appeared in the source of the function that records them. Both passed for the
> entire life of the feature while every recorded value was null. The fields were
> documented as populated, quoted in recorded run summaries as though populated,
> and never were. The tests could not have failed on the data.
>
> **invalid-if:** every test in the suite has been observed failing when the
> behaviour it covers is removed, and that observation is recorded.
### 4.3 Prove a test can fail before trusting it

> **Tier tag:** «REPLACE: [PORTABLE] / [COMPENSATING] / [STANDARD]» — from your own
> run evidence, per the models named at the top of this file

§4.2 says a check that cannot fail is not a check. This is the practice that
catches one: **before trusting any test, break the behaviour it covers and
watch it go red.** Delete the line, invert the branch, stub the function.
Then restore.

A test that has never been observed failing is unverified. An unverified test
is worse than no test, because it manufactures confidence: it reports green
and means nothing. A missing test is an acknowledged gap; a hollow one is a
gap wearing a green tick.

- **Do it at the moment of writing, not later.** Thirty seconds, while the
  behaviour is in your head. Retrofitting it across a suite is an audit.
- **Inject the bug the test claims to catch, not an unrelated one.** A test of
  a classifier's fallback should have the fallback changed; breaking something
  adjacent proves nothing about this test.
- **Sample more than one input, and never only the convenient one.** Injection
  proves a test *can* fail. It does not prove it fails *where the bug is*. A
  test that samples a single value says nothing about the range, and if that
  value happens to be where the buggy and correct behaviour coincide, the test
  passes on broken code and injection will not save you — you would inject the
  bug, see red on some other input, and conclude the test works. Sweep the
  range, or at minimum pick a value that is not the one the implementation
  already special-cases.
- **Restore and re-run.** The point is the red, not the breakage. Leave the
  tree green.
- **For anything with a knob: test that turning it does something, not that it
  exists.** A configurable-but-unapplied parameter passes every signature
  check, every default check, and every presence check. Only exercising the
  effect distinguishes them.
- **Required, not optional, for tests guarding a silent-failure mode.** Empty
  generations, misclassified failures, unwritten fields, unreported
  measurements: these are invisible while broken, so the test is the only
  thing standing between you and a false green. If the test cannot be shown to
  fail, it is not guarding anything.
- **Record that you did it.** A comment naming the injected bug and the input
  that produced the red is enough. The next reader should not have to wonder
  whether the test was ever exercised.

The failure mode this catches is not exotic. Every one of these was a check
that stayed green while the thing it guarded was broken: a source-text
assertion over a field that was never written, a 0% retry failure rate that
was really a success-path bug, a classifier fallback that labelled every
unrecognised error as model incapability, a file count reported from
aggregation that no one checked against a single named record, and a relayed
measurement repeated without re-derivation. One practice catches all five.

There is a sixth, and it is the subtle one. A retry budget was asserted to
cover a stage's worst case, and the test used the mid tier. The mid tier was
the single input where the buggy value and the correct value coincide: a
900-second ceiling times two attempts is 1800 seconds, which is exactly what
the flat budget already returned. Every other tier was wrong. The test was not
missing, not wrong, and not a presence assertion — it sampled the one point on
the curve where the bug was invisible. "Test the boundary" does not help
here, because the test *did* hit a boundary. It hit the one that agreed with
the bug. Assert against several points, and especially against the ones the
implementation had no reason to favour.

> **earned-from:** four tests guarding a new rule were written and passed; two
> of them passed on broken input. One bounded a section body at the wrong
> heading level, so an untagged rule swallowed the section that happened to
> quote the tag names. One checked a region broad enough that the thing it was
> asserting on satisfied it by itself. Both were found only because the bug was
> injected before the test was trusted. Neither would have been found by
> reading the test.
>
> **earned-from (coincidence):** a retry-budget test asserted the budget
> covered a stage's worst case, sampling the mid tier, where a 900s ceiling
> times two attempts equals the 1800s flat budget exactly. High tier needed
> 3000s against that same 1800s cap and was being cut off mid-retry. The test
> was correct, present, and green for the entire life of the bug.
>
> **earned-from (knob):** a verify-gate timeout was made configurable and
> every check passed — the signature took the argument, the default resolved,
> the environment override was honoured. None of them proved the value reached
> the subprocess call. A real 30s suite against a 2s ceiling, asserting a
> TIMEOUT comes back, was the only test that could tell configurable from
> applied.
>
> **invalid-if:** the suite has a mechanism that fails any test whose covered
> behaviour survives deletion, so the check no longer depends on someone
> remembering to do it by hand.
### 4.4 Anchor an edit to text you have actually read

> **Tier tag:** «REPLACE: [PORTABLE] / [COMPENSATING] / [STANDARD]» — from your own
> run evidence, per the models named at the top of this file

An agent editing a file matches on patterns, not on understanding. That is
fine while the anchor is unique and the surrounding text is known. It fails
silently when the anchor overlaps something adjacent: a definition line gets
consumed, a block gets duplicated, and the result still parses.

- **Read the region before editing it.** Not the file, the region. An anchor
  chosen from memory or from a partial view lands wherever it first matches,
  and the first match is not always the one you meant.
- **Read *past* the end of the anchor.** This is the part that bites even when
  you follow the rule above. Reading up to the anchor is enough to place it and
  not enough to see what its tail will consume. An anchor ends where you stop
  typing, and the next line belongs to something else — a `return`, a `def`, a
  closing brace. Read the anchor plus the lines after it, every time.
- **Assert the anchor was unique before relying on it.** One match or none is
  a decision; several is a choice you did not make.
- **Re-read the diff after applying it.** Not the summary the tool prints —
  the actual changed lines. A clobbered definition is obvious in a diff and
  invisible in a "patched successfully" message.
- **Run the suite after any structural edit.** This is what catches the rest.
  Treat that as luck-adjacent rather than reliable: a clobbered test that
  still parses is invisible, and a clobbered one that no longer parses is only
  found because something else happened to import it.

The hazard is not carelessness, it is the edit model. Pattern matching has no
notion of "this line was already part of something else."

> **earned-from:** twice in one session an edit consumed a `def` line it did
> not mean to touch, once in a test file and once in a source file. Both were
> caught by the suite rather than by the edit, and one of them required
> reading the traceback to find, because the surviving file still parsed.
> A third anchor silently did nothing at all and was reported as applied.
>
> **earned-from (why the rule was extended):** after "read the region" was
> written down, an edit still deleted a function's `return` statement. The
> region had been read — up to the end of the anchor and no further. The rule
> as written was satisfied and the failure still happened, which is the
> signature of a rule that names the right hazard at the wrong resolution.
> "Read the region" tells you where to start; it does not tell you to look at
> what comes after the text you matched.
>
> **invalid-if:** edits are applied as structured operations against a parsed
> representation, so an anchor cannot consume adjacent text.
## 5. State must be per-run, never module-global

Per-run audit data must NOT live on a module-level global, or concurrent calls
in one process can bleed run A's data into run B's manifest.

- Pass per-run state as return values / local variables, not module globals.
- **Cement it with a test.** Add a regression test asserting the return shape
  and that two runs in one process get distinct, self-contained state.

> **earned-from:** a cross-run bleed where a module-global cache shared state
> between concurrent stages (from the agent-guardrails-kit reference
> implementation). Rule-out + verified fix (tuple return).

## 6. Product invariants (don't weaken these)

These are the safety-hard rules for TF2autoswap. Every subagent must preserve
them. They are the *summary* of `docs/SECURITY.md` controls; each maps to a
numbered control with a code anchor in that document.

1. **Material safety layer must gate every build path** — wallhack vectors
   (depth-test bypass, unlit shaders, risky proxy targets) are hard-refused
   by `validate_material_set()` in `tf2_material.py`. No bypass, no
   opt-out, no "just this once." Maps to SECURITY.md C1.
   > **earned-from:** the safety layer was built *because* a previous
   > approach (static VMT scanning) missed runtime proxy animation of
   > `$alpha`/`$ignorez`. The proxy detector (`find_risky_proxy_targets()`)
   > closes that gap.

2. **Schema and cache files must have size limits before parsing** —
   `MAX_SCHEMA_SIZE` (200MB) and `MAX_CACHE_SIZE` (100MB) in
   `tf2_schema.py` prevent memory exhaustion DoS. Maps to SECURITY.md
   C2, C3.
   > **earned-from:** security audit (v4.8) found zero size validation
   > in `load_schema()` and cache loaders — both exploitable via
   > crafted input.

3. **Risk acknowledgement is non-optional** — the startup warning and
   `agree` prompt must not be weakened, shortened, or made skippable.
   Maps to SECURITY.md C4.

4. **Prop size fairness warning must fire** — `prop_size_warning()` with
   2.5x threshold is guidance, not enforcement, but must not be removed
   or silently skipped. Maps to SECURITY.md C6.

5. **No cookie/session surface to end users** — cookie/session concepts
   must never appear in user-facing prompts, docs, or error messages.
   This rule exists because a live Steam session credential was once
   caught in AI-generated draft code and had to be rotated.
   > **earned-from:** a live Steam session cookie was generated by an
   > AI agent in draft code for a live-fetch feature; the credential had
   > to be rotated. The rule exists because of this, not hypothetically.

6. **tf2_core.py is pure logic — zero print()/input()** — the core module
   must remain interface-free so a future GUI can replace only the CLI
   layer without touching core or schema. Do not add print(), input(),
   or UI logic to tf2_core.py.

7. **Architecture split is non-negotiable** — `tf2_core.py` (logic),
   `tf2_schema.py` (schema), `tf2_material.py` (safety), `tf2autoswap.py`
   (CLI interface). Do not merge these concerns. Maps to
   `docs/PROJECT_CONTEXT.md`.

## 7. Bounded, single-concern tasks

Agents receive **single-concern, bounded tasks** — one verifiable unit of work,
not "build the whole feature."

- **One writer at a time.** At most one agent may mutate source/tests in a
  given turn. When more than one agent must change code, assign each agent a
  **disjoint file set**, or give each an **isolated git worktree/branch** that
  the orchestrator merges.
- A task prompt should name **one** deliverable (one function, one test file,
  one guardrail), not an end-to-end subsystem.
- Each unit must be independently verifiable (`python3 -m pytest tests/ -q`)
  so a failure is localizable.

> **earned-from:** empirical observation — small batches are what make
> self-hosting safe; a single unbounded prompt is unrecoverable when (not if)
> the runtime flakes mid-task.

## 8. A wedged/looping child is cancelled and respawned, not resumed

When a child implementation agent gets stuck in a loop, hangs, or must be
cancelled mid-task, treat its output as UNTRUSTED and PARTIAL:

- Do NOT resume the wedged agent or reuse its in-progress state — cancel it
  and launch a FRESH child to complete the unit.
- After cancellation, the orchestrator inspects the actual files on disk (§4).
- The fresh child must finish the SAME bounded unit — it repairs/completes
  the partial file and adds anything missing.

> **earned-from:** a child agent launched via the orchestration tool wedged
> mid-task and was cancelled, leaving a source file with a single dropped
> syntax-breaking line and no tests. The orchestrator recovered by reading
> on-disk state, spawning a fresh child to finish the unit, and re-verifying
> (compile + test). (From agent-guardrails-kit reference.)

## 9. Report-back directive (this is how HARMONY improves)

If, while working, you discover:

- a NEW agent-runtime error or crash mode,
- a code footgun, cross-run bleed, or silent-failure path,
- a rule in this file that is wrong, incomplete, or contradicts reality,
- OR any "gotcha" not covered above,

**report it back to the orchestrator** with a concrete reproduction and a
proposed fix. The orchestrator will fold it into this file. Don't silently
work around a problem; surface it.

## 10. Coordinated flow (the pattern that works here)

1. Orchestrator launches an **implementation agent** with this file attached
   and the rules above. Agent edits code + tests, verifies via
   `python3 -m pytest tests/ -q`, reports. (Task is bounded per §7.)
2. Orchestrator **re-verifies on disk** (grep + test + import check) —
   does not trust the self-report alone (§4).
3. Orchestrator launches a **read-only QA agent** (§2) with the same rules,
   to independently confirm. QA reports PASS/FAIL.
4. If QA or the orchestrator finds a gap, loop back to step 1.
5. Any new error/footgun discovered → update §9 + this file + the Amendments
   log below.

No agent commits. The orchestrator holds the final integration view.

> **Anti-pattern: direct orchestrator writes.** The orchestrator should NOT
> edit project code directly — it delegates all mutations to implementation
> agents. When an orchestrator bypasses the delegation layer and edits a core
> file itself, it creates a protocol-violation cascade: the direct write
> introduces untested changes that break tests, and recovery requires
> additional child agents to fix the damage while the orchestrator can no
> longer objectively verify its own work.

> **earned-from (coordinator failure):** when the coordinator dropped, the run
> stayed recoverable because (a) roles are swappable, not hard-wired; (b) each
> agent's task was a bounded unit; (c) per-run state meant nothing shared had to
> be reconstructed. Human oversight bridged the gap. (From agent-guardrails-kit
> reference.)

## Amendments

- **2026-09-09:** Synced from `agent-guardrails-kit/HARMONY.template.md` via `harmony_sync.py`. Added sections that existed in the template but not here:
  - 11. Orchestrator tier is a coordination input, not a given
  - 2.2 An unnameable failure is a classifier defect
  - 4.1 When disk cannot be trusted, two non-shared contexts cross-check
  - 4.2 A check that cannot fail is not a check
  - 4.3 Prove a test can fail before trusting it
  - 4.4 Anchor an edit to text you have actually read

Append-only record of what changed in this file.

- **2026-08-05:** Created from `agent-guardrails-kit` HARMONY.template.md.
  Filled all `«REPLACE»` slots with tf2autoswap-specific facts: fish 4.8
  shell (§1), `wait_for_events` crash (§3), pytest verify command (§2, §4, §7),
  product invariants mapped to SECURITY.md controls (§6). Deleted sections
  that did not apply (orchestrator tier §11 — environment does not currently
  have multiple model tiers; state-directory containment — not applicable to
  this codebase).
- **2026-08-05:** Added §3 (NEVER call wait_for_events) with earned-from the
  2026-08-05 session where it cancelled twice during structure setup.

## Carried from template

## 11. Orchestrator tier is a coordination input, not a given

> **Tier tag:** «REPLACE: [PORTABLE] / [COMPENSATING] / [STANDARD]»

HARMONY §4 assumes *"the orchestrator re-verifies every change on disk"* and
§10 makes the orchestrator hold the final integration view. That assumption is
anchored to the orchestrator being **reliable**. It is not automatically.

- The orchestrator is the §4 verifier. If it runs on a **flaky / free / cheap
  model tier**, its own self-reports AND its on-disk re-checks are **untrusted
  by construction** — that is the exact class of runtime known to strip message
  bodies, crash mid-run, and emit empty generations. It can also mis-perform the
  verify step itself.
- For any run that **mutates code**, one of the following MUST hold:
  1. A **separate QA agent on a stronger tier** independently confirms the work
     (§10 step 3), so the verifier is not the same weak component that built it; OR
  2. The orchestrator performs a **genuine** §4 re-check — compile + test + grep
     the actual diff — and does not short-cut to its own green self-report.
- A weak-tier orchestrator with **no separate QA step** is a single point of
  untrustworthy verification. Treat its "tests pass" as **insufficient** on its
  own.

> **earned-from:** a run orchestrated entirely on a free/cheap model tier
> produced a parallel-edit collision that the orchestrator's own verify step
> did not catch on disk. The weakest link was the verifier. Lesson: §4's safety
> net only exists if a *reliable* party runs it.
