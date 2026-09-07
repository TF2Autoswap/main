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
