# Compiled Pilot Evaluation and Public Arena Plan

> **Status:** Proposed
> **Date:** 2026-09-06
> **Scope:** Steel Onslaught repository
> **Reference project:** [nigrosimone/llms-robot-arena](https://github.com/nigrosimone/llms-robot-arena)
> **Implementation state:** Plan only. This document does not authorize or include implementation.

## 1. Objective

Add a second, explicitly separated evaluation lane to Steel Onslaught in which
an AI system produces a bounded pilot artifact before a match and that frozen
artifact is then evaluated repeatedly without live model calls.

The new lane complements the existing live LLM pilot path:

| Lane | Model participation | Primary question |
| --- | --- | --- |
| Live pilot | The model makes decisions during the match | How does a model behave under live observations, constraints, and uncertainty? |
| Compiled pilot | The model produces a pilot artifact before the match | How well can a model turn a fixed contract into a durable autonomous policy? |

The work must also make evaluation results easier to inspect and share through
a reproducible tournament manifest, side-swapped batteries, portable evidence,
and a public exhibition experience that does not require provider credentials.

This is not a plan to copy another project's code or replace Steel Onslaught's
event-sourced architecture. It adopts useful experimental and product patterns
while preserving Steel Onslaught's contracts, reducers, ledger, replay, and
verification boundaries.

## 2. Why This Is Worth Adding

Steel Onslaught already supports live LLM pilots, deterministic heuristic
pilots, seeded matches, event-ledger reconstruction, round-robin balance runs,
paired candidate evaluation, and independently verifiable evidence. Those
capabilities answer questions that a source-code arena cannot answer.

The missing experiment is a frozen-policy comparison. Today a live model's
provider behavior, latency, context, and output variability are part of the
observed system. A compiled pilot lane would isolate the quality of the policy
artifact from the availability and variability of live inference.

That separation enables four useful comparisons:

1. one model against another under the same generation contract;
2. one-shot generation against iterative development;
3. the same model as a compiled pilot and as a live pilot;
4. the same frozen pilot across engine, arena, and loadout versions.

The public arena portion also addresses a product problem. The current live
demo may require local services or provider configuration. Included frozen
pilots and recorded evidence can provide a useful, inspectable experience with
no API key and no inference dependency.

## 3. Evidence From the Reference Project

The reference project demonstrates several useful patterns:

- a controller is generated before a match and exposed through one narrow
  function contract;
- submitted code is parsed, restricted, and executed with explicit resource
  limits;
- tournaments distinguish quick exhibitions from full round-robin evaluation;
- each seed is run with swapped starting assignments;
- reports record controller hashes, model and harness provenance, rules and
  engine versions, execution budgets, results, and uncertainty;
- replay bundles can be exported, imported, and validated;
- a browser-hosted demonstration runs included controllers without an account,
  provider credential, or live model request;
- evaluation guidance distinguishes one-shot submissions from iteratively tuned
  submissions and treats opponent implementations as black boxes.

These are patterns to adapt. The reference repository did not declare a license
when this plan was written. No source from it may be copied into Steel Onslaught
without an applicable license or explicit permission.

## 4. Existing Steel Onslaught Capabilities to Reuse

Implementation must bind to the current architecture rather than create a
parallel game or evaluation stack.

### 4.1 Pilot boundary

`PilotProtocol.decide(ModelSOPilotObservation) -> ModelSOPilotDecision` is the
canonical per-tick pilot interface. A compiled pilot must satisfy this protocol
or be adapted to it at composition time. Reducers and the match runner must not
know whether a decision originated from a heuristic, frozen artifact, human
command, or live model.

### 4.2 Contract-owned observations and decisions

`ModelSOPilotObservation` already defines the complete information a pilot may
receive. `ModelSOPilotDecision` already validates the action, parameters,
reason code, confidence, considered actions, rationale, and source provenance.
The compiled lane must consume and emit these types without an untyped payload
escape hatch.

### 4.3 Match execution and truth

`DuelExecutor`, `PilotDuelExecutor`, and the normal composition root already
provide the match boundary. The canonical event stream and reducer-owned final
state remain authoritative. A compiled-pilot runtime is an injected effect or
adapter capability, not a second source of match truth.

### 4.4 Replay

`ReplayEngine` reconstructs state by folding canonical events through the same
state transition logic used during live execution. Portable replay work must
package and validate this existing evidence, not replace it with video frames
or an alternate simulation result.

### 4.5 Evaluation and statistics

`so balance` already provides a deterministic round-robin matrix over pilot and
loadout configurations. The learning subsystem already provides exact paired
sign tests, Wilson intervals, explicit sample sizes, and promotion rules. The
new work should extend these surfaces instead of introducing an unrelated
statistics implementation.

## 5. Architectural Decisions

### AD-1: Compiled pilots are a separate lane

The compiled-pilot lane must have an explicit mode and provenance. It must
never silently replace a failed live model request or be reported as live model
behavior.

### AD-2: The artifact is data under a contract

A compiled pilot is a versioned, immutable artifact with a canonical digest.
The generation process and the execution process are separate. Once admitted
to a battery, the artifact cannot change between matches.

The initial artifact format should be selected during implementation design.
Candidates include a constrained declarative policy, WASM module, or sandboxed
program. The format must be chosen by the smallest safe execution boundary, not
by compatibility with the reference project's JavaScript implementation.

### AD-3: Existing contracts remain the game boundary

The artifact receives only `ModelSOPilotObservation` and returns only
`ModelSOPilotDecision`. It cannot read the ledger, opponent implementation,
filesystem, network, wall clock, secrets, host process, or reducer state.

### AD-4: Admission and competitive evaluation are different gates

Admission proves that an artifact is safe, bounded, contract-conforming, and
replay-compatible. Competitive evaluation measures behavior. Passing admission
must never be reported as proof that the pilot is effective.

### AD-5: Fairness conditions are explicit experiment dimensions

Steel Onslaught intentionally supports asymmetric loadouts and scenarios. A
new symmetric benchmark profile should provide a cleaner pilot-only comparison,
but it must not replace the existing scenario batteries.

Every formal pairwise benchmark must run:

- the same declared seed set;
- both seat assignments for every seed;
- the same arena and loadout contracts;
- a pinned engine, rules, prompt, and artifact-contract version;
- a complete, non-cherry-picked result set.

Geometric mirroring should be an additional declared condition rather than
being inferred from seat swapping.

### AD-6: Public reports are projections, not authority

Rankings, dashboards, downloadable reports, and replay pages are projections of
canonical evidence. They may be rebuilt from the tournament manifest and event
ledgers. They may not create or modify match results.

### AD-7: Provenance is part of the result

A result is not adequately identified by model name. The evidence must preserve
the generation method, model identity, provider, reasoning setting, harness,
contract versions, prompt manifest, artifact digest, execution budget, engine
version, seed, seat, scenario, and completion status.

## 6. Proposed Contracts

Names below are provisional. Implementation must first confirm whether an
existing model can be extended without weakening its closed schema.

### 6.1 Compiled pilot artifact

`ModelSOCompiledPilotArtifact` should include:

- artifact ID and schema version;
- artifact format and format version;
- canonical content digest;
- declared pilot ID and compatible observation/decision versions;
- generator provenance reference;
- resource-budget profile reference;
- creation timestamp supplied by the outer workflow;
- optional human-readable description that is never used for execution.

Executable bytes or policy data should live in the artifact store. Contracts
and events should carry references and digests rather than duplicate unbounded
content.

### 6.2 Generation provenance

`ModelSOCompiledPilotGeneration` should include:

- development mode: `one_shot`, `iterative`, or `manual`;
- model and provider identity when applicable;
- reasoning level and harness identity when known;
- prompt-template and source-contract digests;
- attempt and iteration counts;
- opponent-information policy;
- generation budget and observed usage;
- resulting artifact digest;
- terminal generation status.

Unknown values must remain explicitly unknown. They must not be inferred from
filenames or marketing labels.

### 6.3 Admission receipt

`ModelSOCompiledPilotAdmissionReceipt` should record mechanical checks for:

- artifact digest and schema validity;
- allowed imports or capabilities;
- memory, instruction, and wall-time ceilings;
- deterministic response under repeated identical observations where the
  artifact contract requires determinism;
- decision-schema conformity;
- forbidden host access;
- failure and timeout behavior;
- replay compatibility;
- admitted execution profile and contract versions.

Admission is fail-closed. An expired or mismatched receipt cannot be reused for
a different artifact, engine, or execution profile.

### 6.4 Tournament manifest

`ModelSOTournamentManifest` should pin:

- tournament ID, mode, and status;
- ordered participant artifact references;
- arena, loadout, pilot, and runtime contract digests;
- engine and replay schema versions;
- seed set;
- seat-swap and geometric-mirror policy;
- execution and admission profiles;
- ranking method and statistical method;
- expected match matrix;
- output evidence namespace.

The expected match matrix must be computed before execution so missing matches
cannot disappear from the report.

### 6.5 Tournament report

The report projection should contain:

- completed, missing, failed, and excluded matches;
- wins, losses, draws, score, and domain metrics;
- per-seat and per-scenario breakdowns;
- violations, timeouts, and degraded executions;
- sample size and uncertainty;
- participant provenance and artifact digests;
- links or logical references to replay evidence;
- explicit labels for provisional quick exhibitions versus complete formal
  evaluations.

## 7. Work Plan

### Phase 0: Architecture and threat-model spike

1. Inventory all current pilot construction paths and prove the one canonical
   insertion point for a compiled pilot.
2. Compare a declarative policy format, WASM boundary, and sandboxed program
   against the required action space and deployment environments.
3. Document the threat model, including CPU exhaustion, memory exhaustion,
   nondeterminism, covert host access, oversized output, and malformed state.
4. Confirm artifact storage ownership and retention with the existing learning
   artifact protocols.
5. Produce a decision record before selecting an executable format.

**Exit gate:** one approved execution-boundary decision with no second match
engine and no unbounded code execution.

### Phase 1: Artifact and provenance contracts

1. Add closed models for compiled artifacts, generation provenance, execution
   budgets, and admission receipts.
2. Add canonical serialization and digest rules.
3. Add an artifact repository protocol and the minimum local adapter needed by
   tests and CLI workflows.
4. Extend pilot decision provenance so replay can distinguish compiled, live,
   heuristic, and human sources without parsing free text.
5. Add contract tests for unknown fields, digest mismatch, version mismatch,
   oversize artifacts, and incomplete provenance.

**Exit gate:** artifacts and receipts round-trip byte-stably, fail closed on
mismatch, and expose no raw-path authority to callers.

### Phase 2: Compiled pilot adapter and admission gate

1. Implement the selected isolated runtime behind an injected protocol.
2. Adapt its output through `ModelSOPilotDecision` and the existing
   `PilotProtocol` boundary.
3. Enforce capability, memory, compute, output-size, and state-size limits.
4. Define deterministic failure events for timeout, invalid output, runtime
   exception, and admission failure.
5. Ensure the adapter cannot access opponent implementation, canonical state,
   storage, secrets, network, or clock.
6. Prove that two calls with the same artifact, observation, and declared state
   produce the same result when determinism is required.

**Exit gate:** adversarial fixtures cannot escape the runtime; every failure is
typed, bounded, ledger-visible, and replay-safe.

### Phase 3: Compiled-pilot duel lane

1. Add explicit compiled-pilot resolution to the existing composition root.
2. Run compiled pilots through the same match runner and reducer stack as every
   other pilot.
3. Emit exact artifact and generation provenance at match admission.
4. Reject silent fallback from a compiled artifact to a heuristic or live
   model.
5. Add hermetic duels proving identical final live and replay states.
6. Add a same-model compiled-versus-live experiment fixture without claiming
   equivalence between the two modes.

**Exit gate:** compiled matches are indistinguishable from ordinary matches to
reducers but remain unambiguously identified in evidence and projections.

### Phase 4: Fair benchmark protocol

1. Extend the balance harness to materialize its expected match matrix before
   execution.
2. Run every seed with both seat assignments.
3. Add a symmetric benchmark overlay with identical loadouts and equivalent
   information for both participants.
4. Add an optional geometric-mirror condition as a separate manifest field.
5. Keep asymmetric, scenario-varied, and loadout-varied batteries as distinct
   experiment families.
6. Fail the completed report when any expected match is absent, duplicated, or
   run against mismatched contract digests.

**Exit gate:** a full battery proves complete seed and seat coverage and can be
reproduced byte-for-byte from the same manifest and artifacts.

### Phase 5: Ranking and reporting projection

1. Preserve the existing pairwise exact tests for candidate promotion.
2. Add a multi-participant ranking projection suitable for public tournaments.
3. Evaluate Bradley-Terry ranking with seed-grouped bootstrap intervals against
   simpler score and win-rate projections.
4. Keep paired seat assignments in the same resampling unit.
5. Report explicit sample sizes, intervals, draws, violations, timeouts, and
   incomplete runs.
6. Export stable JSON and human-readable report formats from the same typed
   projection.

**Exit gate:** ranking output is reproducible, uncertainty is visible, and a
partial exhibition cannot be mistaken for a completed benchmark.

### Phase 6: Portable replay and evidence bundle

1. Define a versioned bundle containing a manifest, participant provenance,
   artifact digests, canonical event ledgers, replay dependencies, and report
   projection.
2. Validate size, schema, contract digests, event ordering, terminal state, and
   replay reconstruction before accepting an imported bundle.
3. Never execute embedded pilot artifacts while viewing an imported replay.
4. Provide stable logical links between each tournament row and its evidence.
5. Add corruption, truncation, version-skew, and path-traversal tests.

**Exit gate:** an offline verifier can reconstruct every included result from
the bundle without provider access or trust in the report text.

### Phase 7: Public no-key exhibition

1. Package a small set of admitted, frozen pilots with complete provenance.
2. Provide a quick exhibition that completes rapidly and is explicitly labeled
   provisional.
3. Provide a full evaluation option that uses the formal manifest protocol.
4. Allow replay inspection, event inspection, result download, and artifact
   metadata inspection without exposing secrets or execution authority.
5. Make the included experience work without live model credentials.
6. Preserve the frontend as an effect-node projection of canonical evidence.

**Exit gate:** a new visitor can run or inspect a meaningful exhibition without
configuration, while every displayed result remains traceable to evidence.

## 8. Verification Strategy

### Contract verification

- reject unknown and missing fields;
- reject non-canonical or mismatched digests;
- reject incompatible schema, engine, and execution-profile versions;
- prove stable serialization;
- prove no ambient file or environment discovery.

### Runtime containment

- infinite loop and excessive recursion;
- excessive allocation and oversized persistent state;
- filesystem, network, clock, process, thread, and secret access attempts;
- malformed, non-finite, and oversized decisions;
- nondeterministic host APIs;
- runtime termination followed by a clean next match.

### Match and replay

- compiled and control pilots pass through the same reducers;
- final live state equals reconstructed replay state;
- exact artifact provenance survives match start through exported evidence;
- failures and timeouts are reconstructable and cannot become successful
  decisions;
- imported replay viewing never invokes a pilot.

### Tournament completeness

- every participant pair has every declared seed and seat assignment;
- no undeclared seed or participant enters a result;
- duplicate matches fail validation;
- partial and cancelled tournaments remain explicitly incomplete;
- repeated runs produce stable reports for deterministic participants;
- statistical resampling keeps paired seat runs together.

### Public experience

- clean browser with no provider credentials;
- included exhibition can complete and replay;
- manifest, provenance, and replay download agree with displayed results;
- no frontend action mutates canonical match truth;
- visual verification covers tournament progress, incomplete status, replay,
  provenance, and failure states.

## 9. Delivery Slices

Each implementation slice should be separately reviewable:

1. execution-boundary decision and threat model;
2. artifact, provenance, budget, and receipt contracts;
3. isolated runtime and admission gate;
4. compiled pilot composition and replay proof;
5. seat-swapped symmetric benchmark protocol;
6. ranking and report projection;
7. portable evidence bundle;
8. public no-key exhibition.

No slice should combine a new executable sandbox with public upload or remote
deployment. Public submission remains out of scope until containment has its
own adversarial evidence and review.

## 10. Explicit Non-Goals

- Replacing live LLM pilots.
- Replacing the event ledger or reducer-owned state.
- Treating video playback as replay authority.
- Claiming that a compiled pilot and live model measure the same capability.
- Making symmetric matches the only valid Steel Onslaught experiment.
- Accepting arbitrary public code during the first implementation.
- Copying code or assets from an unlicensed repository.
- Inferring model, provider, harness, or development provenance from a filename.
- Using model self-report, a judge model, or manual review as the completion
  gate for artifact admission or match verification.

## 11. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Executable artifacts expand the attack surface | Select an isolated runtime only after a threat-model spike; begin with trusted included artifacts and no public upload. |
| A parallel engine creates competing truth | Reuse `PilotProtocol`, the normal match runner, reducers, ledger, and replay engine. |
| Frozen pilots are reported as live intelligence | Require explicit lane and decision-source provenance in contracts and reports. |
| Seat or arena bias is mistaken for model quality | Pair every seed across both seats and declare geometric mirroring separately. |
| Public rankings overstate weak evidence | Separate quick exhibitions from formal complete evaluations and always show sample size and uncertainty. |
| Artifact provenance is unverifiable | Store canonical digests and generation receipts; label unsupported origin claims as unverified. |
| Imported bundles become an execution vector | Validate data only and never execute embedded artifacts during replay inspection. |
| Reference code creates licensing exposure | Adopt ideas only until the project declares a compatible license or grants explicit permission. |

## 12. Completion Criteria

This initiative is complete only when all of the following are mechanically
demonstrated:

1. A frozen pilot artifact is admitted through bounded, fail-closed checks.
2. The artifact runs through the existing pilot, match, event, reducer, and
   replay boundaries without a second truth path.
3. Its identity and generation provenance survive into canonical evidence.
4. A formal tournament covers its entire declared pair, seed, seat, and mirror
   matrix or is labeled incomplete.
5. An independent verifier can reproduce included results from portable
   evidence without model access.
6. A no-key visitor can inspect a meaningful exhibition and its evidence.
7. Live-pilot and compiled-pilot results cannot be confused in any supported
   report or UI.
8. No implementation source or asset has been copied from the reference
   repository without a compatible license or explicit permission.

## 13. First Implementation Decision

The first implementation ticket should not begin with UI work. It should answer
one question with evidence:

> What is the smallest artifact format and isolation boundary that can produce
> `ModelSOPilotDecision` from `ModelSOPilotObservation` while remaining bounded,
> portable, deterministic when required, and unable to acquire host authority?

Once that decision is recorded, the existing Steel Onslaught architecture
provides the rest of the path: compose the adapter as a pilot, record its
provenance in the ledger, evaluate it through paired batteries, reconstruct it
through replay, and expose the resulting evidence through projections.
