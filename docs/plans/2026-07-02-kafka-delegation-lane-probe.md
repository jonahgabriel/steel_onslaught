# Kafka delegation-lane probe — Phase E gate evidence (R5)

> **Scope:** read-only. No infra was mutated — no publishes, no restarts, no
> topic creation, no consumer connects. Every claim below carries a
> `verified: <date> via <command>` line. This document is the only write
> produced by this task.
> **Author:** probe run 2026-07-02, against `docs/plans/2026-07-02-llm-pilot-plan.md`
> §1 "Kafka delegation lane (contract override, infra hosts) — Phase E" and
> Rev 5 remaining-work item **R5**.

## Verdict

**Gate: evidence-supported to proceed, with one residual unknown.**

- The live topic names + wire DTOs the plan assumes are **confirmed correct**
  on the stability-test lane (`.201`): both declared subscribe topics and all
  five declared publish topics exist, and `node_llm_delegation_call_effect`
  is deployed there (auto-discovered from `omnimarket==0.4.3`) with a
  registered consumer-group subscription on its command topic.
- **Residual unknown:** `onex.cmd.omnimarket.delegation-execute.v1` (the
  command topic the plan's Kafka lane would publish to) has **zero messages
  ever produced** on stability-test (high-watermark 0 on all 6 partitions,
  verified below). Nobody has round-tripped a real
  `ModelLlmDelegationCallRequest` through this exact path yet. Proving that
  round-trip requires an actual publish — a mutation — which is out of scope
  for this read-only probe and is the correct first live-fire step of the
  Phase E *build*, not a precondition for starting it.
- The former dependency gate (aiokafka) is moot either way: the
  recommendation below is a **sync `confluent-kafka` client**, not aiokafka,
  because the game's `decide()`/`EventBus` seam is hard-sync (see §3).

## 1. Local contract read

`omnimarket/src/omnimarket/nodes/node_llm_delegation_call_effect/contract.yaml`
(read at
`/Users/jonah/Code/omni_home/omnimarket/src/omnimarket/nodes/node_llm_delegation_call_effect/contract.yaml`):

```yaml
event_bus:
  subscribe_topics:
    - "onex.cmd.omnimarket.delegation-execute.v1"
    - "onex.cmd.omnibase-infra.delegation-inference-request.v1"
  publish_topics:
    - "onex.evt.omnibase-infra.inference-response.v1"
    - "onex.evt.omnimarket.delegation-call-completed.v1"
    - "onex.evt.omnimarket.delegation-escalation-triggered.v1"
    - "onex.evt.omnimarket.delegation-all-tiers-failed.v1"
    - "onex.evt.omnimarket.delegation-model-degraded.v1"
metadata:
  transport_type: kafka
```

Topics are read straight out of this YAML by
`omnimarket.nodes.contract_topics.contract_subscribe_topics` /
`contract_publish_topics` (`omnimarket/src/omnimarket/nodes/contract_topics.py`)
— there is no separate hardcoded-topic-string surface to cross-check; the
contract *is* the source of truth, confirmed by direct read.

**Two independent request/response pairs share this one node** (two
`handler_routing.handlers` entries):

| Op | Command topic | Request DTO | Handler | Response |
|---|---|---|---|---|
| `execute_delegation_call` ("swarm/A2A path") | `onex.cmd.omnimarket.delegation-execute.v1` | `ModelLlmDelegationCallRequest` | `HandlerLlmDelegationCall` | `ModelLlmDelegationCompletedEvent` → `delegation-call-completed.v1`, or `ModelLlmDelegationAllTiersFailedEvent` → `delegation-all-tiers-failed.v1` |
| `execute_inference_intent` | `onex.cmd.omnibase-infra.delegation-inference-request.v1` | `ModelInferenceIntent` (`omnibase_core.models.delegation.wire`) | `HandlerInferenceIntent` | `ModelInferenceResponseData` → `onex.evt.omnibase-infra.inference-response.v1` |

The plan (`2026-07-02-llm-pilot-plan.md` §1, Phase E) names
`ModelLlmDelegationCallRequest` explicitly — i.e. it targets the
**`execute_delegation_call` / `delegation-execute.v1` row**, not the
inference-intent row. That's the row this probe verified.

### Handler is fully synchronous — confirms the plan's no-asyncio premise

```
handler_llm_delegation_call.py:265   def handle(self, request: ModelLlmDelegationCallRequest) -> (
                                          ModelLlmDelegationCompletedEvent
                                          | ModelLlmDelegationAllTiersFailedEvent
                                          | ModelLlmDelegationCallResult
                                      ):
transport.py:153,194                 with httpx.Client(timeout=timeout_seconds) as client:
```

`grep -n "async def" handler_llm_delegation_call.py transport.py` returns
**no matches** — the entire call path is `httpx.Client` (sync), not
`httpx.AsyncClient`. This independently confirms the plan's §1 claim ("Sync
`handle`, sync `decide()`: no asyncio anywhere in the hot path") for the
in-process lane, and matters for the Kafka lane too: the platform side of
the wire is sync-native: nothing here forces an async client.

### DTO import paths (verified present, not guessed)

```
omnimarket.nodes.node_llm_delegation_call_effect.models.model_llm_delegation_call_request.ModelLlmDelegationCallRequest
omnimarket.nodes.node_llm_delegation_call_effect.models.model_llm_delegation_call_result.ModelLlmDelegationCallResult
omnimarket.models.delegation.llm_cost_routing.model_llm_delegation_completed_event.ModelLlmDelegationCompletedEvent
omnimarket.models.delegation.llm_cost_routing.model_llm_delegation_all_tiers_failed_event.ModelLlmDelegationAllTiersFailedEvent
omnimarket.enums.enum_delegation_failure_class.EnumDelegationFailureClass
omnimarket.enums.enum_cost_basis.EnumCostBasis
omnimarket.enums.enum_usage_source.EnumUsageSource

# The other row's DTOs (NOT what the plan targets, but confirmed live — see §2):
omnibase_core.models.delegation.wire.ModelInferenceIntent
omnibase_core.models.delegation.wire.ModelInferenceResponseData
```

`ModelLlmDelegationCallRequest` required fields: `request_id`,
`correlation_id`, `causation_id`, `model_id`, `endpoint_ref`, `prompt`,
`prompt_hash`, `timeout_seconds`. `secret_ref` carries a *name*, never a
literal key (`llm/client_http.py`-adjacent doctrine: name-not-value,
resolved fail-closed at the effect boundary). One docstring wrinkle worth
flagging for whoever builds Phase E: the model's docstring says "prompt is
in-memory only ... must never be persisted or published to Kafka" — read in
context that's a caution against re-emitting prompt text into *other*
(evidence/ledger) topics, not a ban on this model being the payload of its
own primary command topic (`subscribe_topic_metadata` in the contract
explicitly names `ModelLlmDelegationCallRequest` as the schema for
`delegation-execute.v1`). Still, don't let this model's fields leak into the
game's own local evidence-event payloads verbatim if a future Kafka-lane
change adds cross-logging.

`omnimarket==0.4.3` is not installed in the game's venv today
(`uv run --no-sync python3 -c "import importlib.metadata as m; m.version('omnimarket')"`
→ `PackageNotFoundError`) — consistent with divergence **D3** in the plan's
Rev 5 reconciliation table (Rev 4's reuse directive not yet applied).

## 2. Live probe (.201, read-only)

### Reachability

```
$ ssh -o BatchMode=yes -o ConnectTimeout=8 jonah@192.168.86.201 "echo SSH_OK; date"
SSH_OK
Thu Jul  2 09:49:21 PM EDT 2026
```
verified: 2026-07-02 via the command above — SSH reachable.

### Which lane runs the node

```
$ ssh jonah@192.168.86.201 "docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'"
```
verified: 2026-07-02 via the command above. Findings:

- **No `dev`-lane container is running at all** (0 containers) — matches
  `omni_home/CLAUDE.md`'s runtime lane table ("dev (optional) ... not in
  last census"). Any live check today has to target **stability-test**
  (documented as the preferred proof lane for synthetic integration
  evidence) or `prod`/`judge` (read-only per doctrine).
- `omninode-stability-test-runtime`, `-runtime-effects`, `-runtime-worker`
  are all `Up 6 hours (healthy)`.

```
$ ssh jonah@192.168.86.201 "docker logs omninode-stability-test-runtime-effects --tail 5000 2>&1 | grep -i 'node_llm_delegation_call_effect'"
```
verified: 2026-07-02 via the command above — repeating, every ~5 minutes,
across **all three** stability-test runtime containers (main, effects,
worker):
```
[INFO] omnibase_infra.runtime.auto_wiring.discovery: Discovered contract: node_llm_delegation_call_effect (effect) from omnimarket 0.4.3
```
This confirms the node is deployed and live-registered on stability-test,
sourced from the same `omnimarket` package version the plan assumes
(`0.4.3`).

### Broker location + reachability

```
$ ssh jonah@192.168.86.201 "docker ps --filter name=redpanda --format '{{.Names}}\t{{.Ports}}'"
```
verified: 2026-07-02 — three brokers, one per lane. stability-test:
`0.0.0.0:39092->19092/tcp`. prod: `0.0.0.0:49092->19092/tcp`. judge:
`0.0.0.0:59092->19092/tcp`. (This corrects the task brief's guessed
`dev broker :19092, effects :39092` — there is no separate "effects" broker;
`19092` is the redpanda **internal** listener, `39092`/`49092`/`59092` are
the **per-lane host-mapped** ports, and there is no `dev` broker running at
all right now.)

```
$ ssh jonah@192.168.86.201 "docker exec omnibase-infra-stability-test-redpanda rpk cluster info --brokers localhost:19092"
```
verified: 2026-07-02 — `BROKERS: ID 0*  HOST 100.109.203.94  PORT 39092`.
**The broker's advertised listener is a Tailscale IP (`100.109.203.94`), not
the LAN IP (`192.168.86.201`).** A Kafka client can dial either address for
the initial TCP bootstrap, but the broker's own metadata response — which
the client library follows for every subsequent produce/fetch — points at
`100.109.203.94:39092`. A game host without Tailscale reachability to that
address will complete the bootstrap handshake and then fail silently on the
first real produce/consume. Verified reachable from *this* probe host (which
has Tailscale joined):
```
$ nc -z -w3 100.109.203.94 39092  → succeeded
$ nc -z -w3 192.168.86.201 39092  → succeeded
```
verified: 2026-07-02 via the two `nc` commands above, run from the probing
session's host. **Whichever machine actually runs `so run --loadout ... `
against the Kafka lane must independently confirm Tailscale reachability to
`100.109.203.94`** — this is not guaranteed for every laptop.

### Topic inventory

```
$ ssh jonah@192.168.86.201 "docker exec omnibase-infra-stability-test-redpanda rpk topic list --brokers localhost:19092"
```
verified: 2026-07-02 via the command above. All 7 contract-declared topics
exist on the stability-test broker (name, partitions, replicas):

| Topic | Partitions | Replicas |
|---|---|---|
| `onex.cmd.omnimarket.delegation-execute.v1` | 6 | 1 |
| `onex.cmd.omnibase-infra.delegation-inference-request.v1` | 6 | 1 |
| `onex.evt.omnibase-infra.inference-response.v1` | 6 | 1 |
| `onex.evt.omnimarket.delegation-call-completed.v1` | 6 | 1 |
| `onex.evt.omnimarket.delegation-escalation-triggered.v1` | 6 | 1 |
| `onex.evt.omnimarket.delegation-all-tiers-failed.v1` | 6 | 1 |
| `onex.evt.omnimarket.delegation-model-degraded.v1` | 6 | 1 |

Also independently confirmed via the live introspection endpoint:
`curl http://192.168.86.201:18085/v1/introspection/manifest` (HTTP 200,
verified: 2026-07-02) contains `delegation-execute`, `delegation-execute.v`,
and the `handlers.handler_llm_delegation_call` module path — the manifest
agrees with the static contract read in §1.

### Consumer wiring (corrected finding — see methodology note)

```
$ ssh jonah@192.168.86.201 "docker exec omnibase-infra-stability-test-redpanda rpk group list --brokers localhost:19092" > full-groups.txt   # 522 lines, captured to a file, NOT piped through head
$ grep -i 'delegation-execute\|llm_delegation_call' full-groups.txt
```
verified: 2026-07-02 via the two commands above (redirected to a file this
time — see methodology note below). Result:

```
stability-test.omnimarket.node_llm_delegation_call_effect.consume.0.1.0.__i.stability-test-effects.__t.onex.cmd.omnibase-infra.delegation-inference-request.v1   Stable
stability-test.omnimarket.node_llm_delegation_call_effect.consume.0.1.0.__i.stability-test-effects.__t.onex.cmd.omnimarket.delegation-execute.v1                 Stable
stability-test.omnimarket.node_swarm_subtask_state_reducer.consume.1.0.0.__i.stability-test-main.__t.onex.cmd.omnimarket.delegation-execute.v1                   Stable
```

A registered consumer group whose name literally embeds
`node_llm_delegation_call_effect`, contract version `0.1.0` (matches
`contract.yaml: node_version: {0,1,0}`), and runtime instance
`stability-test-effects` (matches `descriptor.runtime_profiles: [effects]`)
**exists and is subscribed to `onex.cmd.omnimarket.delegation-execute.v1`**.
A downstream reducer (`node_swarm_subtask_state_reducer`) is also
independently subscribed to the same topic. The full downstream fan-out for
the publish side is likewise registered and Stable: `delegation-call-completed.v1`,
`delegation-all-tiers-failed.v1`, and `delegation-escalation-triggered.v1`
each have 3–4 independent consumer groups (`node_delegation_routing_feedback_reducer`,
`node_llm_delegation_projection`, `node_swarm_fanout_orchestrator`,
`node_swarm_subtask_state_reducer`) — a live swarm/delegation consumption
graph, not just a provisioned-but-orphaned topic.

**Caveat, checked and reported honestly:** `rpk group describe` on this
group (and, as a sanity check, on every other group tested — including ones
proven to have processed real historical traffic, e.g.
`node_llm_inference_effect`) reports `STATE Dead / MEMBERS 0` at the instant
of the probe:
```
$ ssh jonah@192.168.86.201 "docker exec omnibase-infra-stability-test-redpanda rpk group describe 'stability-test.omnimarket.node_llm_delegation_call_effect.consume.0.1.0' --brokers localhost:19092"
GROUP   stability-test.omnimarket.node_llm_delegation_call_effect.consume.0.1.0
STATE   Dead
MEMBERS 0
TOTAL-LAG 0
```
verified: 2026-07-02. Because this "Dead / 0 members" snapshot is uniform
across every group tested regardless of proven traffic history, it reads as
this platform's consumers being short-lived/on-demand (connect, poll,
commit, disconnect) rather than persistent daemons — **not** as evidence
that this specific subscription is broken. Treat "no member connected right
now" as inconclusive rather than negative.

### Message traffic (the actual residual gap)

```
$ ssh jonah@192.168.86.201 "docker exec omnibase-infra-stability-test-redpanda rpk topic describe <topic> --brokers localhost:19092 -p"
```
verified: 2026-07-02, run per topic. High-watermarks (sum is illustrative,
per-partition values checked):

| Topic | Traffic | Reading |
|---|---|---|
| `onex.cmd.omnimarket.delegation-execute.v1` | **0 across all 6 partitions** | Never produced to, on stability-test, prod, *or* judge (checked all three lanes) |
| `onex.cmd.omnibase-infra.delegation-inference-request.v1` | 177–226 per partition | Proven live — the inference-intent row is exercised regularly |
| `onex.evt.omnibase-infra.inference-response.v1` | 154–195 per partition | Matches the above — round-trip proven |
| `onex.evt.omnimarket.delegation-call-completed.v1` | 0–2 per partition | A handful of historical messages — plausibly a smoke test, not regular traffic |
| `onex.evt.omnimarket.delegation-escalation-triggered.v1` | 3–10 per partition | Light but nonzero |
| `onex.evt.omnimarket.delegation-all-tiers-failed.v1` | 0 across all 6 | Expected — rare failure path |
| `onex.evt.omnimarket.delegation-model-degraded.v1` | 0 across all 6 | Expected — rare threshold-triggered event |

**This is the one honest gap.** Everything the contract declares for the
`execute_delegation_call` row is provisioned and subscribed, but nobody has
ever pushed a real `ModelLlmDelegationCallRequest` through
`delegation-execute.v1` on any lane. The row is infrastructure-ready, not
integration-proven.

### Methodology note (a mistake caught and corrected mid-probe)

An earlier pass of this probe piped `rpk group list` through `| tee file |
head -60`. `head` closing its read end after 60 lines sent `SIGPIPE`
upstream and truncated the capture to 78 of 522 lines — which produced a
**false negative** ("no consumer group for this node exists"). Re-running
without a truncating pipe (redirect straight to a file) surfaced the correct
522-line list and reversed that finding. Flagging this because it's exactly
the kind of silent-truncation bug that produces a confidently wrong "gate
closed" verdict; the corrected, complete-capture evidence is what's reported
above.

## 3. The sync-seam wrinkle — evaluated with evidence

The constraint: `PilotProtocol.decide()` is called synchronously inside the
tick loop (`reducers/pilot_tick.py:234`), `src/steel_onslaught/llm/` bans
`asyncio` imports (source-scan, plan §Verification), and the game's
`EventBus` protocol (`src/steel_onslaught/bus/protocol.py`) is
non-`async def` throughout. omnimarket's Kafka stack
(`omnimarket/pyproject.toml:46`) is `aiokafka` — an async client. Three
options, evaluated:

**Option A — `confluent-kafka` (sync, C-based/librdkafka) as a game
extra.** This is not a novel choice for this platform: `confluent_kafka` is
already an established, sanctioned sync-Kafka pattern *in this codebase*,
used today for sync produce/consume in tooling that has the same
synchronous-caller constraint the game has:
```
omnimarket/src/omnimarket/nodes/node_emit_daemon/health_probe.py:69   from confluent_kafka import Consumer
omnimarket/src/omnimarket/nodes/node_emit_daemon/health_probe.py:248  record = consumer.poll(remaining)
omnibase_infra/src/omnibase_infra/backends/backend_probe.py:105       from confluent_kafka.admin import AdminClient
```
`confluent-kafka` is also already a declared dependency in
`omnibase_infra/pyproject.toml:62` ("C-based high-performance client").
Ships prebuilt wheels for macOS arm64 (this dev machine's platform) and
Linux — no local `librdkafka` build required. **Recommended.**

**Option B — a sync wrapper around `aiokafka`** (spin a private event loop
per call, e.g. `asyncio.run(...)` inside a sync method). Rejected: this
reintroduces exactly the asyncio-adjacent surface the source-scan guard
exists to keep out of `llm/`, adds event-loop lifecycle bugs (nested loops,
loop-per-call overhead) for no benefit over a client that's natively sync,
and there's no existing precedent for it anywhere in the platform to copy
correctness from.

**Option C — REST/thin-publish ingress.** Checked for an existing HTTP
ingress that fronts `delegation-execute.v1` (would let the game stay
HTTP-only, reusing its existing `httpx` dependency). None found:
`curl http://192.168.86.201:18085/openapi.json` → 404; the only live HTTP
surfaces on stability-test are the introspection manifest
(`/v1/introspection/manifest`, read-only) and the projection-api container
(`omnimarket-stability-test-projection-api`, port `13002`, a read
surface). Building a bespoke publish-proxy endpoint would also cut against
platform doctrine (`feedback_dashboard_renders_projections_not_rest`,
`feedback_bus_is_the_transport`: HTTP is a thin publisher *into* the bus,
never a bespoke ad hoc endpoint) and is explicitly platform-side work, not
game-side. Rejected for this lane.

**Recommendation: Option A.** Add `confluent-kafka` as a `kafka` optional
extra on the game (not a hard dependency — the in-process lane, Phases
A–D, needs none of this), implement `LlmBusDelegationClient` behind the
existing `ProtocolLlmClient` seam (`llm/schemas.py`) using a sync
`Producer`/`Consumer` pair scoped to one request/response round trip per
call (publish `ModelLlmDelegationCallRequest` to `delegation-execute.v1`,
poll `delegation-call-completed.v1` / `delegation-all-tiers-failed.v1` for
the matching `correlation_id`, with the REMAIN-fallback timeout the pilot
already needs for every other failure class per plan §2 point 4). No
asyncio import is introduced; the source-scan guard stays green by
construction.

## 4. Remaining build steps (Phase E, not yet started)

1. Add `omnimarket>=0.4.3` as a normal dependency (per plan §1 note 7 / Rev
   4) — currently absent from `pyproject.toml` (divergence D3). Prefer a
   real PyPI version constraint over a `[tool.uv.sources]` local path entry
   — the existing `omnibase-core`/`omnibase-spi` local-path sources
   (`pyproject.toml:62-64`) already hardcode
   `/Users/jonah/Code/omni_home/...` absolute paths, a pre-existing Rule-6
   violation outside this task's declared surface; don't extend that
   pattern to a third dependency.
2. Add `confluent-kafka` as a `kafka` extra (Option A above).
3. Implement `LlmBusDelegationClient(ProtocolLlmClient)` in `llm/` — publish
   to `onex.cmd.omnimarket.delegation-execute.v1`, consume
   `delegation-call-completed.v1` (success) and `delegation-all-tiers-failed.v1`
   (terminal failure) filtered by `correlation_id`, with a hard timeout that
   feeds the pilot's existing REMAIN-fallback path.
4. Contract override wiring: which lane (`in_process` vs `kafka`) is active
   is contract configuration per plan §1 — add the override entry to
   `llm/contract.yaml` per that design, gated to infra hosts.
5. **First live-fire test is a real mutation** — publish one
   `ModelLlmDelegationCallRequest` to stability-test and confirm a
   `ModelLlmDelegationCompletedEvent` comes back. This is the one thing this
   read-only probe could not do and should not attempt; it's the natural
   first integration test once the client above exists, run with the same
   read/write posture the rest of Phase E build work gets (dev-lane-start
   is pre-authorized; stability-test is the proof lane; no prod/judge
   mutation).
6. Confirm Tailscale reachability (`100.109.203.94:39092`) from whichever
   host will actually run the Kafka-lane game process (§2 broker
   reachability note) before relying on it for a demo.

## Out of scope for this probe (confirmed, not touched)

No publishes, no topic creation, no consumer connects, no container
restarts, no writes anywhere except this file. `prod` and `judge` lanes were
only read (`docker ps`, `rpk topic describe` for the one topic, to confirm
the zero-traffic finding held platform-wide) — never mutated.
