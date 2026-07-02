# LLM Pilot — nondeterministic personas over a replaceable seam

> **Status:** draft, awaiting review/iteration.
> **Author:** generated 2026-07-02.
> **Depends on:** the ONEX restructure (Phases 0–5, landed on `feat/armor-degrading-pool`)
> and the initiative system.

## Core principle (confirmed by code exploration)

Replay reconstructs state by folding the **recorded ledger events** through the
pure fold. The fold is pure (AST-enforced). So replay is idempotent *by
construction* — it does not matter whether those events were generated
deterministically or by a coin-flipping LLM. The events are the source of truth;
the fold just replays them. A StarCraft replay faithfully reconstructs a game
whose original players made nondeterministic human decisions — same principle.

Concretely, the verified findings:

- **`verify_replay_validity` already validates ledger-consistency, not re-run
  equality.** It folds the events *already in the ledger* through a fresh
  `MatchStateFold` and compares against the live fold's state. It never
  re-invokes a pilot or re-rolls an RNG. An LLM producing nondeterministic
  decisions generates a different ledger each run, but each ledger is internally
  consistent and replays faithfully. **The replay gate needs no change.**
- **The pilot seam is structural.** `PilotProtocol.decide(observation) →
  decision` is a `@runtime_checkable` Protocol. Any class with that method
  satisfies it — no inheritance, no spec-system entry, no archetype-Literal
  change required.
- **What breaks is *cross-run* determinism** (same seed → identical stdout /
  identical win matrix). That is a real, documented property we are choosing to
  relax for LLM matches. The replay-validity *gate* (score = 0 if replay ≠ live)
  does NOT break — it only ever compares a run against its own ledger.

## Design

### 1. A replaceable LLM client seam — `pilots/llm_client.py`

A `ProtocolLlmClient` Protocol with one method:

```python
class ProtocolLlmClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str, **opts: Any) -> str: ...
```

This is the provider seam — OpenAI, Anthropic, local Ollama, or a stub all
implement it. The pilot depends on the Protocol, never on a specific SDK. Ship:

- **`OpenAICompatibleClient`** — uses `httpx` (already a transitive dep from
  `omnibase_core`); calls `/v1/chat/completions`. Works with OpenAI, Ollama,
  vLLM, LM Studio via `base_url` override. Configurable `base_url`, `api_key`,
  `model`, `temperature`.
- **`StubLlmClient`** — deterministic rule-based responses for tests / offline
  dev (no network). Maps observation → canned decision so the LLM pilot can be
  developed and tested fully offline.

### 2. The LLM pilot — `pilots/llm.py`

`LLMPilot(client: ProtocolLlmClient, persona: LlmPersona)`. Implements
`decide(observation) → ModelSOPilotDecision`:

1. Serializes the observation to a compact text prompt (own hp / heat /
   pressure / weapons / mode + noisy enemy readings).
2. Prepends the **persona system prompt** (the asymmetry source).
3. Calls `client.complete(...)`, parses the JSON response →
   `{action, action_params, confidence, rationale}`.
4. Validates the action against the canonical vocabulary
   (`available_actions(observation)`), falling back to REMAIN if the LLM returns
   something invalid or unparseable (robustness — a malformed LLM response never
   crashes the match).
5. Returns a `ModelSOPilotDecision`. The LLM's natural-language `rationale` is
   carried in a new optional field (see §4).

### 3. Persona library — `pilots/llm_personas.py`

A few canned personas that create genuine behavioral asymmetry (the thing
learning needs, and the thing that makes LLM-vs-LLM matches interesting):

- **`BERSERKER`** — closes to point-blank, fires every tick, ignores heat.
- **`SNIPER`** — maintains max range, fires only on high-confidence locks, vents
  proactively.
- **`OPPORTUNIST`** — waits for the enemy to overcommit, punishes overheating.

Each is just a system-prompt string + default decision opts. Easy to add more.

### 4. Decision schema extension — `pilots/schemas.py`

Add `rationale: str | None = None` to `ModelSOPilotDecision` (currently
`extra="forbid"` drops freeform reasoning). Flows through the REST inspector and
WebSocket bridge automatically (they serialize the whole payload). The CLI
renderer ignores it (backward-compatible). Heuristic pilots leave it `None`.

### 5. Wiring — `match/runner.py` + `cli/`

- `MatchRunner` accepts an optional `pilots_override: dict[str, PilotProtocol] |
  None`. When set, `run()` uses it instead of `_pilot_from_spec`. This is the
  clean injection point — no spec-system, registry, or archetype-Literal changes.
- A CLI flag `--llm-persona-a` / `--llm-persona-b` on `so run` that builds
  `LLMPilot` instances for each side from an env-configured client + chosen
  personas, and passes them as the override. (Lean: flags on `so run` rather
  than a separate command, so one entrypoint handles both heuristic and LLM
  matches.)
- `assemble_match_live` stays as-is for the deterministic scored-match path
  (learning loop, leaderboard). LLM matches are a separate composition that
  does not need scoring / leaderboard.

### 6. What explicitly changes about determinism (honest documentation)

Update `docs/plans/2026-07-02-determinism-boundaries.md`:

- **Replay-validity (per-run, ledger-consistency):** UNCHANGED. Still holds;
  still the gate.
- **Cross-run determinism (same seed → identical output):** HOLDS for heuristic
  pilots, DOES NOT HOLD for LLM pilots. Two LLM matches with the same seed
  produce different ledgers (different LLM decisions), but each replays
  correctly.
- The learning-loop determinism chain (`test_learn_e2e.py`) applies only to
  heuristic-pilot matches; LLM matches are not part of that chain.

## Execution order

1. **Schema extension** (`rationale` field) — additive, low-risk.
2. **LLM client seam + Stub** — the replaceable Protocol + a deterministic stub
   (no network needed to develop / test).
3. **LLM pilot + personas** — built against the stub first (deterministic,
   testable offline).
4. **OpenAI-compatible client** — the real provider impl.
5. **Wiring** — `pilots_override` in `MatchRunner`, CLI flags on `so run`.
6. **Documentation** — the determinism-boundaries update.

## Verification

- Stub-based unit tests: `LLMPilot` parses responses, validates actions, falls
  back on garbage, carries rationale.
- An LLM-vs-LLM match (persona A vs persona B) runs end-to-end and produces a
  *different* ledger each run (proving nondeterminism) that *replays correctly*
  (proving idempotency).
- Heuristic-pilot matches: fully unchanged (same-seed byte-identical,
  replay-validity holds, 848 tests green).
- With a real API key: a live LLM-vs-LLM match with emergent behavior.

## Open questions (for adjustment)

- **Provider:** default to OpenAI-compatible (works with OpenAI + local servers
  via `base_url`). Easy to add an Anthropic client later — the Protocol seam
  makes it a drop-in.
- **Determinism mode:** build it genuinely nondeterministic (stated preference)
  — no seed-freezing on the LLM call. The replay-idempotency story holds. If we
  later want optional seeded determinism for an LLM pilot, it's a
  `temperature=0` + record/replay overlay on the same seam.
- **Scope of the CLI:** `--llm-persona-a` / `--llm-persona-b` flags on `so run`,
  or a separate `so run-llm` command? Leaning toward flags on `so run` (one
  command, persona selection per side).

## Out of scope

- The learning loop driving LLM pilots (LLM duels are nondeterministic, so
  side-swap symmetry breaks — that is a separate, larger design for "learning
  from LLM play" via graded metrics or recorded transcripts).
- Adding `"llm"` as a first-class spec archetype (the `pilots_override` bypass
  is lower-friction; can promote to spec-faithful later if wanted).
- Frontend UI changes for rationale display (the field flows through
  automatically; rendering it is a frontend task).
