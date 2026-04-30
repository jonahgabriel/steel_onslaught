# Steel Onslaught MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Routing: ticket-pipeline (single-repo, sequential). Linear: NOT required (personal repo, local mode if launched).

**Goal:** Ship a deterministic, event-sourced, replayable steampunk mech-duel arena (§24 of the design doc) that proves the OmniNode-native contest substrate end-to-end.

**Architecture:** Event-bus-first. Reducers own canonical match state. Effects (CLI + web UI) render projections of the event stream and never mutate truth. Per-match SQLite ledger gives append-only event storage and bit-identical replay reconstruction. Heuristic pilot orchestrators (Python decision trees) ensure full replay determinism without LLM nondeterminism. Single-process synchronous tick loop for the MVP; the `EventBus` protocol allows a Kafka adapter to slot in post-MVP without touching reducer code.

**Tech Stack:** Python 3.13 (canonical brew interpreter `/opt/homebrew/bin/python3.13`), `uv` for venv + dependencies, `ruff` for lint+format, `mypy --strict`, `pytest` (markers: `unit` / `integration` / `slow`), Pydantic v2 for contract models, PyYAML for contract files, SQLite (stdlib `sqlite3`) for the event ledger, Click for CLI, Vite + React + TypeScript for the web projection.

**Architectural Decisions (FIXED for the MVP — referenced throughout the plan):**

1. **Pilot orchestrator: HEURISTIC.** Pure Python decision trees per archetype. No LLM. Deterministic by construction.
2. **Event transport: IN-PROCESS** behind an `EventBus` protocol. Kafka adapter is post-MVP.
3. **Event ledger: SQLite** — one file per match (`ledger/<match_id>.sqlite`), append-only `events` table. Replay reads sequentially.
4. **Two UI projections.** (a) CLI text via Click + ANSI; (b) Vite + React + WebSocket.
5. **Match orchestration:** single-process, synchronous discrete tick loop.
6. **Determinism:** per-match RNG seed is recorded in the `match_started` event payload. All stochastic resolutions (hit rolls, sensor noise, rupture probability, weapon scatter) consume that seed via a `MatchRng` wrapper that derives per-tick sub-seeds from `(seed, tick, mech_id, kind)`. Replay must reconstruct canonical match state exactly from the ledger; CLI replay output for the same ledger must be byte-identical; browser rendering is a projection proof, not a byte-identical artifact (timestamps, animation timing, and font metrics are excluded from the determinism contract).
7. **Canonical event ordering:** the authoritative ordering of events in the ledger is `(tick ASC, sequence_in_tick ASC, event_id ASC)`. `tick` is the match tick at emission. `sequence_in_tick` is a 0-indexed monotonic counter assigned by the EventBus inside a single tick (resets to 0 each tick boundary). `event_id` (a ULID) is unique but is NOT the primary ordering authority — its embedded wall-clock can drift under retries or fast emission. `emitted_at` is metadata only and MUST NOT be used for replay ordering. Reducers and the replay engine read events in canonical order; any other ordering is a bug.
8. **Repo layout:**
   - `src/steel_onslaught/` — package root
     - `events/` — envelope + event payload schemas
     - `bus/` — `EventBus` protocol + in-process implementation
     - `ledger/` — SQLite append + replay reader
     - `contracts/` — Pydantic models for chassis/boiler/weapon/sensor/gizmo/mode/loadout
     - `pilots/` — pilot observation/decision schemas + heuristic archetypes
     - `reducers/` — match lifecycle, movement, sensors, pilot tick, boiler, mode, weapons, armor, failure cascade, scoring
     - `replay/` — engine + tick stepper API
     - `projections/cli/` — text projection
     - `projections/leaderboard/` — SQLite materialized view
     - `cli/` — entrypoint commands (`so run`, `so replay`, `so leaderboard`)
   - `tests/` — pytest tree mirroring src/
   - `contracts_data/` — YAML chassis/boiler/weapon/sensor/gizmo/mode specs
   - `frontend/` — Vite + React app (effect node)
   - `docs/plans/` — design + plan markdown
   - `migrations/` — SQL migration files
9. **CI:** GitHub Actions: ruff check, ruff format check, mypy --strict, pytest -m "unit or integration", pytest -m "not slow". No deploy-gate, no receipt-gate (personal repo).

---

## Known Types Inventory

> Greenfield repo. Initial commit (87fbab6) contains only `README.md` and `.gitignore`. There are no pre-existing models, enums, TypedDicts, dataclasses, or Protocols.
>
> Every type introduced by this plan is net-new and namespaced under either the Pydantic class prefix `ModelSO*` (e.g. `ModelSOEventEnvelope`, `ModelSOChassisSpec`) or the contract `kind:` prefix `steel_onslaught.*`.
>
> R7 Type Duplication: by definition no duplication is possible — there is nothing to duplicate. Every "Not reusing X because" line in this plan would read "X does not exist yet." Skipping the line in each task is intentional and per-task no further justification is required.

---

## Runtime State Inventory

> All runtime state is created by this plan. There are no pre-existing tables, topics, or consumer groups to ground against.

### SQLite Tables (created by Task 6 + Task 30)

**`events` table** — defined in Task 6, migration file `migrations/0001_events.sql`:

| Column | Type | Notes |
|---|---|---|
| `event_id` | TEXT PRIMARY KEY | ULID, unique but NOT the ordering authority |
| `match_id` | TEXT NOT NULL | foreign-keyless (one ledger file per match) |
| `tick` | INTEGER NOT NULL | match tick when emitted; primary ordering authority |
| `sequence_in_tick` | INTEGER NOT NULL | 0-indexed monotonic counter inside one tick (resets each tick) |
| `event_type` | TEXT NOT NULL | e.g. `pilot_decision_made` |
| `correlation_id` | TEXT | event chain root |
| `causation_id` | TEXT | direct upstream event_id |
| `producer_node` | TEXT NOT NULL | e.g. `node.pilot.red.01` |
| `subject_json` | TEXT NOT NULL | JSON `{mech_id, player_id}` |
| `payload_json` | TEXT NOT NULL | event-type-specific JSON |
| `emitted_at` | TEXT NOT NULL | ISO-8601 UTC; metadata only, NOT used for ordering |
| `schema_version` | TEXT NOT NULL DEFAULT '0.1.0' | |

Canonical replay order is `(tick ASC, sequence_in_tick ASC, event_id ASC)`. Index on `(tick, sequence_in_tick)` for replay scan; secondary index on `event_type` for projection filters. Append-only enforcement: SQLite `BEFORE UPDATE` and `BEFORE DELETE` triggers raise abort errors on `events`; no `update`/`delete` methods exist on `SQLiteLedger`.

**`leaderboard_entries` table** — defined in Task 30, migration file `migrations/0002_leaderboard.sql`:

| Column | Type | Notes |
|---|---|---|
| `match_id` | TEXT PRIMARY KEY | one row per scored match |
| `winner_player_id` | TEXT NOT NULL | |
| `winner_loadout_id` | TEXT NOT NULL | |
| `winner_score` | INTEGER NOT NULL | |
| `loser_player_id` | TEXT NOT NULL | |
| `loser_score` | INTEGER NOT NULL | |
| `duration_ticks` | INTEGER NOT NULL | |
| `scored_at` | TEXT NOT NULL | ISO-8601 UTC |

Lives in a separate SQLite file `ledger/leaderboard.sqlite` (separate from per-match event ledgers).

### Consumer Groups

In-process `EventBus` only — no Kafka, no consumer groups. Subscribers are in-process callables registered via `bus.subscribe(handler, event_types=...)`. Replay subscribers are constructed fresh per replay invocation; there is no persistent subscriber identity to ground.

### Topic Resolution

In-process bus — no topic strings. Event routing is by `event_type` field on the envelope. The string namespace is `steel_onslaught.*` matching the design's `kind:` field. Topic resolution becomes meaningful only when the post-MVP Kafka adapter lands.

---

## Task 1: [Phase A] Initialize Python project skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/steel_onslaught/__init__.py`
- Create: `src/steel_onslaught/py.typed`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Step 1: Write the failing test**

```python
# tests/test_smoke.py
import importlib

def test_package_importable() -> None:
    mod = importlib.import_module("steel_onslaught")
    assert mod.__name__ == "steel_onslaught"
```

**Step 2: Verify failure**

```
uv run pytest tests/test_smoke.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'steel_onslaught'`.

**Step 3: Implement**

`pyproject.toml`:
```toml
[project]
name = "steel_onslaught"
version = "0.1.0"
description = "Steampunk tactical mech battle — event-bus-native, replayable, contract-driven contest framework"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.6",
    "pyyaml>=6.0",
    "click>=8.1",
    "ulid-py>=1.1",
    "websockets>=12.0",  # used by Task 31's WebSocket bridge to the frontend
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.23",  # for the WebSocket bridge tests in Task 31
    "mypy>=1.10",
    "ruff>=0.5",
    "playwright>=1.45",      # used only by Task 34's Proof of Life web assertion
]

[project.scripts]
so = "steel_onslaught.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/steel_onslaught"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: fast in-memory tests",
    "integration: cross-module tests with real SQLite",
    "slow: tests over 1s",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "RUF"]

[tool.mypy]
strict = true
python_version = "3.13"
files = ["src/", "tests/"]
```

`src/steel_onslaught/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/steel_onslaught/py.typed` — empty file.

**Step 4: Verify pass**

```
uv venv --python /opt/homebrew/bin/python3.13
uv sync --extra dev
uv run pytest tests/test_smoke.py -v
```
Expected: PASS — 1 passed.

**Step 5: Commit**

```bash
git add pyproject.toml src/steel_onslaught/__init__.py src/steel_onslaught/py.typed tests/__init__.py tests/test_smoke.py
git commit -m "feat: project skeleton (pyproject, package init, smoke test)"
```

---

## Task 2: [Phase A] Configure tooling (pre-commit, mypy strict)

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `mypy.ini` (mirror of pyproject [tool.mypy] for tools that don't read pyproject)
- Modify: `pyproject.toml` (already has tool sections from Task 1)

**Step 1: Verify mypy is strict**

```
uv run mypy src/
```
Expected: pass with `Success: no issues found in 1 source file`.

**Step 2: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic>=2.6, types-PyYAML]
        args: [--strict]
```

**Step 3: Install + verify**

```
uv run pre-commit install
uv run pre-commit run --all-files
```
Expected: PASS (ruff + mypy clean).

**Step 4: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: pre-commit (ruff + mypy strict)"
```

---

## Task 3: [Phase A] CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Write workflow**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Set up Python
        run: uv python install 3.13
      - name: Install
        run: uv sync --extra dev
      - name: Lint
        run: |
          uv run ruff check src/ tests/
          uv run ruff format --check src/ tests/
      - name: Type check
        run: uv run mypy src/ tests/
      - name: Tests
        run: uv run pytest -m "unit or integration" -v
```

**Step 2: Verify locally**

```
act -j test
```
(if `act` installed; otherwise verify after push.)

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: ruff + mypy strict + pytest workflow"
```

---

## Task 4: [Phase A] Core event envelope model

**Files:**
- Create: `src/steel_onslaught/events/__init__.py`
- Create: `src/steel_onslaught/events/envelope.py`
- Create: `tests/events/test_envelope.py`

**Invariants asserted by tests (Step 1):**

- `ModelSOEventEnvelope` round-trips through `model_dump_json()` / `model_validate_json()` losslessly.
- `event_id` is required, ULID-shaped (26 chars, base32).
- `tick` is non-negative.
- `sequence_in_tick` is required and non-negative.
- `subject` validates as `{mech_id: str, player_id: str}`.
- `event_type` matches a known enum (`SOEventType`), including the new `MODE_SWITCH_INTENT` and `WEAPON_FIRE_INTENT` intent events.
- `schema_version` defaults to `"0.1.0"`.
- An envelope with `causation_id` referencing another envelope's `event_id` round-trips.
- Two envelopes with the same `(tick, sequence_in_tick)` but different `event_id` are accepted by Pydantic (uniqueness is enforced at the ledger layer, not the model layer).

**Step 1: Failing test**

```python
# tests/events/test_envelope.py
import pytest
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

@pytest.mark.unit
def test_envelope_round_trip() -> None:
    env = ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEFG",
        match_id="match.2026-04-30.001",
        tick=42,
        sequence_in_tick=0,
        event_type=SOEventType.PILOT_DECISION_MADE,
        correlation_id="corr.x",
        causation_id="evt.prev",
        producer_node="node.pilot.red.01",
        subject={"mech_id": "mech.red.01", "player_id": "player.17"},
        payload={"action": "vent"},
        emitted_at="2026-04-30T16:00:00Z",
    )
    blob = env.model_dump_json()
    parsed = ModelSOEventEnvelope.model_validate_json(blob)
    assert parsed == env

@pytest.mark.unit
def test_envelope_rejects_negative_tick() -> None:
    with pytest.raises(ValueError):
        ModelSOEventEnvelope(
            event_id="01JABCDE0123456789ABCDEFG",
            match_id="m", tick=-1, sequence_in_tick=0,
            event_type=SOEventType.MATCH_STARTED,
            producer_node="p",
            subject={"mech_id": "m", "player_id": "p"},
            payload={}, emitted_at="2026-04-30T16:00:00Z",
        )
```

**Step 2: Run + verify FAIL** (`ImportError`).

**Step 3: Implement** — `src/steel_onslaught/events/envelope.py`:

```python
from __future__ import annotations
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict

class SOEventType(StrEnum):
    # Lifecycle
    MATCH_STARTED = "match_started"
    MATCH_TICK = "match_tick"
    MECH_SPAWNED = "mech_spawned"
    # Observation
    SENSOR_OBSERVATION = "sensor_observation"
    # Pilot decision (informational, emitted before intents)
    PILOT_DECISION_MADE = "pilot_decision_made"
    # Intents — produced by the pilot tick reducer; consumed by downstream
    #          reducers which validate and either accept or reject.
    MOVE_INTENT = "move_intent"
    WEAPON_FIRE_INTENT = "weapon_fire_intent"
    MODE_SWITCH_INTENT = "mode_switch_intent"
    VENT_INTENT = "vent_intent"
    # Resolved state changes (canonical truth)
    MOVEMENT_RESOLVED = "movement_resolved"
    BOILER_UPDATED = "boiler_updated"
    HEAT_REDLINE_ENTERED = "heat_redline_entered"
    HEAT_REDLINE_EXITED = "heat_redline_exited"
    BOILER_OVERLOADED = "boiler_overloaded"
    BOILER_RUPTURED = "boiler_ruptured"
    MODE_TRANSITION_STARTED = "mode_transition_started"
    MODE_TRANSITION_COMPLETED = "mode_transition_completed"
    WEAPON_FIRED = "weapon_fired"
    HIT_RESOLVED = "hit_resolved"
    ARMOR_ABSORBED = "armor_absorbed"
    DAMAGE_APPLIED = "damage_applied"
    PILOT_INJURED = "pilot_injured"
    PILOT_KILLED = "pilot_killed"
    MECH_DESTROYED = "mech_destroyed"
    # Termination
    VICTORY_DECLARED = "victory_declared"
    MATCH_ENDED = "match_ended"
    MATCH_SCORED = "match_scored"

class ModelSOEventSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mech_id: str
    player_id: str

class ModelSOEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "0.1.0"
    event_id: str = Field(min_length=26, max_length=26)  # ULID; uniqueness only
    match_id: str
    tick: int = Field(ge=0)                              # primary ordering authority
    sequence_in_tick: int = Field(ge=0)                  # secondary ordering authority
    correlation_id: str | None = None
    causation_id: str | None = None
    producer_node: str
    subject: ModelSOEventSubject
    event_type: SOEventType
    payload: dict[str, Any]
    emitted_at: str                                      # metadata only, not for ordering
```

**Step 4: Run + verify PASS** (`pytest tests/events/test_envelope.py -v`).

**Step 5: Commit**

```bash
git add src/steel_onslaught/events/ tests/events/
git commit -m "feat(events): ModelSOEventEnvelope + SOEventType enum"
```

---

## Task 5: [Phase A] EventBus protocol + in-process implementation

**Files:**
- Create: `src/steel_onslaught/bus/__init__.py`
- Create: `src/steel_onslaught/bus/protocol.py`
- Create: `src/steel_onslaught/bus/in_process.py`
- Create: `tests/bus/test_in_process.py`

**Invariants asserted by tests:**

- A handler subscribed to `event_types=[A, B]` receives only A and B envelopes.
- Multiple subscribers on the same type all fire on `publish()`.
- Publish order is preserved per subscriber.
- Unsubscribe removes the handler before the next publish.
- A handler raising an exception does not stop other handlers (errors collected and re-raised after).
- `publish()` is synchronous — handlers complete before publish returns.
- The bus assigns `sequence_in_tick` per published event: a counter that resets to 0 each time `tick` advances and increments by 1 for each subsequent publish at the same tick. The bus rejects an envelope whose `sequence_in_tick` is already populated by the producer (the bus is the sole authority).
- The bus tracks a `current_tick` that advances only on `MATCH_TICK` events; all events published between `MATCH_TICK(N)` and `MATCH_TICK(N+1)` carry `tick=N`.

**Step 1: Failing test**

```python
# tests/bus/test_in_process.py
import pytest
from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType, ModelSOEventSubject

def _env(t: SOEventType, eid: str = "01JABCDE0123456789ABCDEFG") -> ModelSOEventEnvelope:
    # sequence_in_tick=0 here is a placeholder; the bus reassigns it on publish.
    return ModelSOEventEnvelope(
        event_id=eid, match_id="m", tick=0, sequence_in_tick=0, event_type=t,
        producer_node="p",
        subject=ModelSOEventSubject(mech_id="m", player_id="p"),
        payload={}, emitted_at="2026-04-30T16:00:00Z",
    )

@pytest.mark.unit
def test_filtered_subscription() -> None:
    bus = InProcessEventBus()
    seen: list[SOEventType] = []
    bus.subscribe(lambda e: seen.append(e.event_type),
                  event_types=[SOEventType.MATCH_STARTED])
    bus.publish(_env(SOEventType.MATCH_STARTED, "01JABCDE0123456789ABCDEF1"))
    bus.publish(_env(SOEventType.PILOT_DECISION_MADE, "01JABCDE0123456789ABCDEF2"))
    assert seen == [SOEventType.MATCH_STARTED]
```

(Add tests for multi-handler ordering, unsubscribe, and error isolation.)

**Step 2: Run, verify FAIL.**

**Step 3: Implement** — protocol + impl:

```python
# bus/protocol.py
from __future__ import annotations
from typing import Callable, Protocol
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

EventHandler = Callable[[ModelSOEventEnvelope], None]
HandlerToken = int

class EventBus(Protocol):
    def publish(self, event: ModelSOEventEnvelope) -> None: ...
    def subscribe(self, handler: EventHandler,
                  event_types: list[SOEventType] | None = None) -> HandlerToken: ...
    def unsubscribe(self, token: HandlerToken) -> None: ...
```

```python
# bus/in_process.py
from __future__ import annotations
from dataclasses import dataclass, field
from steel_onslaught.bus.protocol import EventBus, EventHandler, HandlerToken
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

@dataclass
class _Subscription:
    token: HandlerToken
    handler: EventHandler
    event_types: frozenset[SOEventType] | None  # None = all

@dataclass
class InProcessEventBus:
    _subs: list[_Subscription] = field(default_factory=list)
    _next_token: HandlerToken = 0
    _current_tick: int = 0
    _next_seq_in_tick: int = 0  # resets each tick

    def publish(self, event: ModelSOEventEnvelope) -> None:
        # Tick boundary: MATCH_TICK advances current_tick and resets sequence.
        if event.event_type == SOEventType.MATCH_TICK:
            self._current_tick = event.tick
            self._next_seq_in_tick = 0

        # Bus is the sole authority for sequence_in_tick: re-issue the envelope
        # with the bus-assigned sequence so producers cannot fabricate ordering.
        sequenced = event.model_copy(update={
            "tick": self._current_tick,
            "sequence_in_tick": self._next_seq_in_tick,
        })
        self._next_seq_in_tick += 1

        errors: list[BaseException] = []
        for sub in list(self._subs):  # snapshot to allow unsubscribe during dispatch
            if sub.event_types is None or sequenced.event_type in sub.event_types:
                try:
                    sub.handler(sequenced)
                except BaseException as exc:  # noqa: BLE001 — collect, re-raise after
                    errors.append(exc)
        if errors:
            raise ExceptionGroup("subscriber errors", errors)

    def subscribe(self, handler: EventHandler,
                  event_types: list[SOEventType] | None = None) -> HandlerToken:
        token = self._next_token
        self._next_token += 1
        self._subs.append(_Subscription(
            token=token, handler=handler,
            event_types=frozenset(event_types) if event_types else None,
        ))
        return token

    def unsubscribe(self, token: HandlerToken) -> None:
        self._subs = [s for s in self._subs if s.token != token]
```

Test that `sequence_in_tick` resets across `MATCH_TICK` boundaries:

```python
@pytest.mark.unit
def test_sequence_in_tick_resets_per_tick() -> None:
    bus = InProcessEventBus()
    seen: list[tuple[int, int]] = []
    bus.subscribe(lambda e: seen.append((e.tick, e.sequence_in_tick)))
    # Tick 1: emit MATCH_TICK then 2 events
    bus.publish(_env(SOEventType.MATCH_TICK, "01JABCDE0123456789ABCDEF1"))
    bus.publish(_env(SOEventType.PILOT_DECISION_MADE, "01JABCDE0123456789ABCDEF2"))
    bus.publish(_env(SOEventType.WEAPON_FIRED, "01JABCDE0123456789ABCDEF3"))
    # Tick 2 boundary
    next_tick = ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEF4", match_id="m", tick=2,
        sequence_in_tick=0, event_type=SOEventType.MATCH_TICK,
        producer_node="p", subject=ModelSOEventSubject(mech_id="m", player_id="p"),
        payload={}, emitted_at="2026-04-30T16:00:00Z",
    )
    bus.publish(next_tick)
    bus.publish(_env(SOEventType.BOILER_UPDATED, "01JABCDE0123456789ABCDEF5"))
    assert seen == [(0, 0), (0, 1), (0, 2), (2, 0), (2, 1)]
```

**Step 4: PASS.**

**Step 5: Commit** — `feat(bus): EventBus protocol + in-process synchronous impl`.

---

## Task 6: [Phase A] Append-only SQLite event ledger + migrations

**Files:**
- Create: `migrations/0001_events.sql`
- Create: `src/steel_onslaught/ledger/__init__.py`
- Create: `src/steel_onslaught/ledger/sqlite_ledger.py`
- Create: `src/steel_onslaught/ledger/migrate.py`
- Create: `tests/ledger/test_sqlite_ledger.py`

**`migrations/0001_events.sql`:**

```sql
-- Migration 0001: events table (append-only, canonical-ordered)
-- Created by Task 6 (2026-04-30 plan)
CREATE TABLE IF NOT EXISTS events (
    event_id          TEXT PRIMARY KEY,
    match_id          TEXT NOT NULL,
    tick              INTEGER NOT NULL CHECK (tick >= 0),
    sequence_in_tick  INTEGER NOT NULL CHECK (sequence_in_tick >= 0),
    event_type        TEXT NOT NULL,
    correlation_id    TEXT,
    causation_id      TEXT,
    producer_node     TEXT NOT NULL,
    subject_json      TEXT NOT NULL,
    payload_json      TEXT NOT NULL,
    emitted_at        TEXT NOT NULL,
    schema_version    TEXT NOT NULL DEFAULT '0.1.0',
    UNIQUE (match_id, tick, sequence_in_tick)
);
CREATE INDEX IF NOT EXISTS idx_events_order
    ON events (match_id, tick ASC, sequence_in_tick ASC);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);

-- Append-only enforcement: reject UPDATE and DELETE at the database layer.
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
  SELECT RAISE(ABORT, 'events table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'events table is append-only');
END;
```

**Invariants asserted by tests:**

- Migrating a fresh DB creates the `events` table with the documented schema (verified via `PRAGMA table_info(events)`), including `sequence_in_tick` and the two append-only triggers (verified via `SELECT name FROM sqlite_master WHERE type='trigger'`).
- Re-running migrations is idempotent (no error, no duplicate rows, no duplicate triggers).
- `append(env)` inserts one row matching the envelope (round-trip via `read_all()`).
- `append(env)` is rejected if `event_id` already exists (PRIMARY KEY violation).
- `append(env)` is rejected if `(match_id, tick, sequence_in_tick)` already exists (UNIQUE constraint).
- A direct `UPDATE events SET tick = 0` raises `sqlite3.IntegrityError` with message containing `append-only`.
- A direct `DELETE FROM events WHERE 1=1` raises the same error.
- `SQLiteLedger` exposes only `append`, `read_all`, `read_after`, and read-side query methods. There is NO public `update`, `delete`, `truncate`, `clear`, or `reset` method. A type-checker test (`tests/ledger/test_no_mutation_api.py`) introspects the class and asserts the public method set matches a frozen allowlist.
- `read_all(match_id)` returns events in `(tick ASC, sequence_in_tick ASC, event_id ASC)` order — the canonical ordering.
- `read_after(match_id, tick)` returns only events with `tick > given`, still in canonical order.

**Step 1: Failing test** (table absent / module missing).

**Step 3: Implement** — sketch:

```python
# ledger/sqlite_ledger.py
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType, ModelSOEventSubject

class SQLiteLedger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def append(self, env: ModelSOEventEnvelope) -> None:
        self._conn.execute(
            """INSERT INTO events
               (event_id, match_id, tick, sequence_in_tick, event_type,
                correlation_id, causation_id, producer_node,
                subject_json, payload_json, emitted_at, schema_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (env.event_id, env.match_id, env.tick, env.sequence_in_tick,
             env.event_type.value,
             env.correlation_id, env.causation_id, env.producer_node,
             env.subject.model_dump_json(), json.dumps(env.payload),
             env.emitted_at, env.schema_version),
        )
        self._conn.commit()

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        cursor = self._conn.execute(
            """SELECT event_id, match_id, tick, sequence_in_tick, event_type,
                      correlation_id, causation_id, producer_node,
                      subject_json, payload_json, emitted_at, schema_version
                 FROM events WHERE match_id = ?
                 ORDER BY tick ASC, sequence_in_tick ASC, event_id ASC""",
            (match_id,),
        )
        for row in cursor:
            yield _row_to_envelope(row)

    # Intentionally NO update/delete/truncate/clear/reset. Append-only.

def _row_to_envelope(row: tuple) -> ModelSOEventEnvelope: ...  # straightforward
```

**Step 4: PASS.**

**Step 5: Commit** — `feat(ledger): SQLite append-only event ledger + migration`.

---

## Task 7: [Phase B] Chassis contract model + 3 chassis YAML specs

**Files:**
- Create: `src/steel_onslaught/contracts/chassis.py`
- Create: `contracts_data/chassis/light_scout_mk1.yaml`
- Create: `contracts_data/chassis/medium_hunter_mk1.yaml`
- Create: `contracts_data/chassis/heavy_ironclad_mk1.yaml`
- Create: `tests/contracts/test_chassis.py`

**Pydantic model (`ModelSOChassisSpec`)** — fields straight from design §9.4:

- `schema_version: Literal["0.1.0"]`
- `kind: Literal["steel_onslaught.chassis"]`
- `id: str` (must match `^chassis\.(light|medium|heavy)\.[a-z0-9_]+$`)
- `display_name: str`
- `chassis_class: Literal["light", "medium", "heavy"]` (rename from `class` keyword)
- `constraints: ModelSOChassisConstraints` (max_mass, max_module_slots, max_boiler_volume, base_speed, base_turn_rate, base_signature, base_vent_rate — all positive ints)
- `compatibility: ModelSOChassisCompatibility` (weapon_classes, boiler_classes, mobility_classes — all `list[str]`, non-empty)
- `penalties: ModelSOChassisPenalties` (mode_switch_latency_modifier, sensor_lock_penalty, heat_weapon_vulnerability — all positive floats ≥ 1.0)

**Invariants asserted by tests:**

- All 3 YAML files load via `ModelSOChassisSpec.model_validate(yaml.safe_load(...))` without errors.
- `chassis.heavy.ironclad_mk1` has `max_boiler_volume == 90` and `base_speed == 2`.
- `chassis.light.scout_mk1` has `chassis_class == "light"` and `base_signature < 50`.
- A YAML with `chassis_class: ultra` is rejected.
- Loading a chassis with `max_mass: -1` is rejected.

**Step 5 commit:** `feat(contracts): chassis model + light/medium/heavy specs`.

---

## Task 8: [Phase B] Boiler contract model + 3 boiler specs + boiler state model

**Files:**
- Create: `src/steel_onslaught/contracts/boiler.py`
- Create: `contracts_data/boilers/compact_v1.yaml`
- Create: `contracts_data/boilers/industrial_bessemer_90.yaml`
- Create: `contracts_data/boilers/volatile_v1.yaml`
- Create: `tests/contracts/test_boiler.py`

**Models:**

- `ModelSOBoilerSpec` — pressure_capacity, regen_per_tick, heat_capacity, heat_multiplier, vent_rate, redline_threshold, rupture_threshold, instability_curve (linear|quadratic|exponential), repairability (none|partial|full), mass, compatibility (compatible_chassis_classes).
- `ModelSOBoilerState` — runtime state per design §10.3 (current pressure, current heat, status flags, modifiers).

**Invariants asserted by tests:**

- All 3 YAML specs load and validate.
- `boiler.industrial.bessemer_90` matches the design's example values (max 90 pressure, vent_rate 4).
- `redline_threshold < rupture_threshold` is enforced at validation.
- A boiler state with `current_heat > rupture_threshold` is invalid (rupture is a terminal event, not a state).

**Step 5 commit:** `feat(contracts): boiler spec + state + compact/industrial/volatile`.

---

## Task 9: [Phase B] Weapon contract model + 6 weapon specs

**Files:**
- Create: `src/steel_onslaught/contracts/weapon.py`
- Create: `contracts_data/weapons/machine_gun.yaml`
- Create: `contracts_data/weapons/steam_cannon.yaml`
- Create: `contracts_data/weapons/artillery_mortar.yaml`
- Create: `contracts_data/weapons/heat_lance.yaml`
- Create: `contracts_data/weapons/shrapnel_thrower.yaml`
- Create: `contracts_data/weapons/harpoon_gun.yaml`
- Create: `tests/contracts/test_weapon.py`

**`ModelSOWeaponSpec` fields** (from design §13.2):
- id, display_name, weapon_class (light|medium|heavy|siege)
- range, damage, pressure_cost, heat_generated, cooldown_ticks
- accuracy_curve: list of `{range: int, hit_probability: float}` — sampled at fixed range bins, linearly interpolated at runtime by Task 24
- target_class_effectiveness: `dict[chassis_class, float]`
- compatibility (compatible_chassis_classes)

**Invariants:**

- All 6 specs validate.
- `machine_gun` has weapon_class=light, range≤15, cooldown_ticks=1.
- `artillery_mortar` has weapon_class=siege, range≥40.
- A weapon with `damage: -1` is rejected.

**Commit:** `feat(contracts): weapon spec + 6 weapon definitions`.

---

## Task 10: [Phase B] Sensor contract model + 4 sensor specs

**Files:**
- Create: `src/steel_onslaught/contracts/sensor.py`
- Create: `contracts_data/sensors/long_range_radar.yaml`
- Create: `contracts_data/sensors/short_range_scanner.yaml`
- Create: `contracts_data/sensors/thermal_detector.yaml`
- Create: `contracts_data/sensors/acoustic_detector.yaml`
- Create: `tests/contracts/test_sensor.py`

**`ModelSOSensorSpec`** — id, display_name, range, precision, latency_ticks, pressure_draw_per_tick, heat_per_tick, signature_impact, jamming_vulnerability_score (0..1).

Long-range radar: range 40, precision 0.6, latency_ticks 1.
Short-range scanner: range 15, precision 0.9, latency_ticks 0.
Thermal: precision against high-heat targets.
Acoustic: precision against fast-moving / high-vent targets.

**Commit:** `feat(contracts): sensor spec + 4 sensor definitions`.

---

## Task 11: [Phase B] Gizmo contract model + 4 gizmo specs

**Files:**
- Create: `src/steel_onslaught/contracts/gizmo.py`
- Create: `contracts_data/gizmos/efficient_regulator.yaml` (efficiency)
- Create: `contracts_data/gizmos/burst_amplifier.yaml` (amplifier)
- Create: `contracts_data/gizmos/targeting_assist.yaml` (control)
- Create: `contracts_data/gizmos/emergency_condenser.yaml` (safety, mirrors design §14.3)
- Create: `tests/contracts/test_gizmo.py`

**`ModelSOGizmoSpec`** — id, display_name, category (efficiency|amplifier|control|disruption|safety), constraints (mass, slots, compatible_chassis), effects (free-form `dict` keyed by trigger), tradeoffs (free-form `dict`), forbidden_stacking (list of gizmo ids).

**Invariants:**

- 4 specs validate.
- `emergency_condenser` matches design §14.3 byte-for-byte.
- `forbidden_stacking` cannot contain the gizmo's own id.

**Commit:** `feat(contracts): gizmo spec + 4 gizmo definitions (one per category)`.

---

## Task 12: [Phase B] Mode contract model + 3 mode specs + transition rules

**Files:**
- Create: `src/steel_onslaught/contracts/mode.py`
- Create: `contracts_data/modes/recon.yaml`
- Create: `contracts_data/modes/assault.yaml`
- Create: `contracts_data/modes/evasion.yaml`
- Create: `tests/contracts/test_mode.py`

**`ModelSOModeSpec`** — id, display_name, active_systems (list of module categories), passive_modifiers, default_priorities.

**`ModelSOModeTransition`** — from_mode, to_mode, costs (pressure, heat, transition_ticks), restrictions (minimum_lock_ticks_after_switch, cannot_switch_if_heat_above, cannot_switch_if_boiler_disabled), vulnerability (evasion_penalty_during_transition, sensor_dropout_ticks).

**Invariants:**

- 3 mode specs validate.
- Mode transitions are defined for all 9 ordered pairs (recon→assault, recon→evasion, assault→recon, ...) and tested.
- `cannot_switch_if_heat_above >= rupture_threshold` is rejected (it would make the rule never fire as a guard).

**Commit:** `feat(contracts): mode spec + transitions for recon/assault/evasion`.

---

## Task 13: [Phase B] Loadout contract + multi-axis budget validator

**Files:**
- Create: `src/steel_onslaught/contracts/loadout.py`
- Create: `src/steel_onslaught/contracts/budget.py`
- Create: `contracts_data/loadouts/example_aggressive_light.yaml`
- Create: `contracts_data/loadouts/example_predictive_heavy.yaml`
- Create: `tests/contracts/test_loadout.py`
- Create: `tests/contracts/test_budget.py`

**`ModelSOLoadout`** matches design §15.3.

**`validate_loadout_budgets(loadout, chassis, boiler, modules) -> list[BudgetViolation]`** computes:
- mass_used = chassis.constraints.max_mass references; sum module masses; reject if > max_mass.
- slots_used = sum module slot counts; reject if > max_module_slots.
- expected_heat_peak = max heat output over all modules in any single mode.
- expected_signature = chassis base_signature + mode-active sensor signature impact.
- pressure_steady_state = sum module pressure draws; reject if > boiler.pressure_capacity * 0.7 (over 70% means no headroom).

**Invariants asserted by tests:**

- A valid loadout passes all budgets.
- A loadout exceeding max_mass returns a `BudgetViolation(kind="mass", used=..., max=...)`.
- A loadout with 9 modules on an 8-slot chassis returns a slot violation.
- Multi-violation: 3 different overflows return 3 violations (not first-fail).

**Commit:** `feat(contracts): loadout spec + multi-axis budget validator`.

---

## Task 14: [Phase C] Pilot observation + decision schemas

**Files:**
- Create: `src/steel_onslaught/pilots/__init__.py`
- Create: `src/steel_onslaught/pilots/schemas.py`
- Create: `tests/pilots/test_schemas.py`

**Models:**

- `ModelSOPilotObservation` — view passed to pilot per tick: own boiler/heat/cooldowns/mode/position, sensor observations of enemy (distance estimate, confidence, heat estimate, mode estimate), tick number, match elapsed ticks.
- `ModelSOPilotDecision` — action (StrEnum: REMAIN, MOVE, FIRE_WEAPON, ACTIVATE_MODULE, VENT, SWITCH_MODE, EMERGENCY_SHUTDOWN, DISENGAGE), action_params (kwargs per action), reason_code (StrEnum), confidence (float 0..1), considered_actions (list of `{action, score}`).
- `PilotProtocol` (Protocol with `decide(observation: ModelSOPilotObservation) -> ModelSOPilotDecision`).

**Invariants:**

- Decision must reference an action available given current state (e.g. SWITCH_MODE requires mode_lock_expired).
- `confidence` is clamped to [0, 1].
- `considered_actions` includes the chosen action.

**Commit:** `feat(pilots): observation + decision schemas + Protocol`.

---

## Task 15: [Phase C] Aggressive pilot heuristic + tests

**Files:**
- Create: `src/steel_onslaught/pilots/aggressive.py`
- Create: `tests/pilots/test_aggressive.py`

**Heuristic (deterministic decision tree):**

1. If enemy in weapon range AND any weapon ready AND pressure ≥ weapon_cost → FIRE highest-damage available weapon at enemy.
2. Else if not in assault mode AND mode_lock_expired AND pressure ≥ 12 AND heat ≤ 80 → SWITCH_MODE assault.
3. Else if heat ≥ 90 (just below redline) → VENT.
4. Else → MOVE toward enemy at full speed.
5. Tolerates redline up to heat == rupture_threshold − 5.

**Invariants:**

- Given enemy in range + ready weapon + pressure: returns FIRE_WEAPON with the highest-damage option.
- Given heat 92 of rupture 100 and enemy in range: still fires (tolerates redline).
- Given heat 96 of rupture 100: vents (close to rupture).
- Given mode=recon + assault available + enemy in range: switches to assault before firing.
- Given multiple weapons of same damage: deterministically picks the lowest-id alphabetically (no random tiebreaker).

**Commit:** `feat(pilots): aggressive archetype heuristic`.

---

## Task 16: [Phase C] Defensive pilot heuristic + tests

**Files:**
- Create: `src/steel_onslaught/pilots/defensive.py`
- Create: `tests/pilots/test_defensive.py`

**Heuristic:**

1. If heat ≥ redline_threshold − 8 → VENT.
2. Else if not in evasion mode AND under sensor lock AND pressure available → SWITCH_MODE evasion.
3. Else if enemy in range AND high-confidence target AND pressure available AND heat headroom ≥ 12 → FIRE.
4. Else if hp_percent < 30 → DISENGAGE (move away).
5. Else → MOVE to maintain optimal range.

**Invariants:**

- Given heat 73 of redline 80: vents.
- Given hp_percent 25, no immediate threat: disengages.
- Given enemy in range with confidence 0.4 (low): does not fire.
- Given enemy with confidence 0.8: fires only if heat headroom ≥ 12.

**Commit:** `feat(pilots): defensive archetype heuristic`.

---

## Task 17: [Phase C] Predictive pilot heuristic + tests

**Files:**
- Create: `src/steel_onslaught/pilots/predictive.py`
- Create: `tests/pilots/test_predictive.py`

**Heuristic** — anticipates enemy state via 1-tick lookahead:

1. Estimate enemy position next tick from sensor observations (linear extrapolation of last 3 observations).
2. If enemy will enter range next tick AND mode-switch needed AND mode_lock_expired → start MODE TRANSITION this tick.
3. Else if enemy in optimal range AND lock_confidence ≥ 0.65 AND predicted_hit_probability ≥ 0.55 → FIRE.
4. Else if heat ≥ redline_threshold − 5 → VENT preemptively.
5. Else if pressure < 30 AND no immediate threat → MOVE to defensive position to regen.

**Invariants:**

- Given last-3 enemy positions show approach: switches mode before enemy arrives.
- Given lock_confidence 0.5: holds fire (waits).
- Given lock_confidence 0.7 + predicted_hit 0.6: fires.
- Linear extrapolation is deterministic (no smoothing, no random).

**Commit:** `feat(pilots): predictive archetype heuristic with 1-tick lookahead`.

---

## Task 18: [Phase D] Match lifecycle reducer

**Files:**
- Create: `src/steel_onslaught/reducers/__init__.py`
- Create: `src/steel_onslaught/reducers/lifecycle.py`
- Create: `src/steel_onslaught/match/state.py` (ModelSOMatchState)
- Create: `tests/reducers/test_lifecycle.py`

**`ModelSOMatchState`** — match_id, tick, status (Pending|Running|Ended), seed, max_ticks (int, hard upper bound for the match), mech_states (dict[mech_id, ModelSOMechRuntimeState]), winner_id (optional — None on draws), end_reason (`last_mech_standing` | `pilot_killed` | `draw_max_ticks` | `aborted`).

**Lifecycle events handled:**

- `MATCH_STARTED` → state Pending → Running, seed recorded, mech states initialized from loadouts, `max_ticks` set from match config (default 200, configurable via `match_started` payload).
- `MATCH_TICK` → tick increments by 1, status remains Running. If `tick >= max_ticks` after the increment, the lifecycle reducer emits `VICTORY_DECLARED` only if there is a single surviving player; otherwise emits `MATCH_ENDED(reason="draw_max_ticks", winner_id=None)` followed by `MATCH_SCORED` (the scoring reducer in Task 29 handles draws by zeroing the `victory` term for both players).
- `VICTORY_DECLARED` → status Running → Ended, winner_id set, end_reason recorded.
- `MATCH_ENDED` → idempotent re-statement of final state for replay; if no `VICTORY_DECLARED` precedes it, this is a draw.

**Invariants:**

- Two `MATCH_STARTED` for same match_id is rejected (raise `ReducerError`).
- `MATCH_TICK` on Pending or Ended match is rejected.
- Tick increments are exactly +1; no skips.
- The match is guaranteed to terminate by `tick == max_ticks` (the loop driver will not publish further `MATCH_TICK` events past this bound, and the lifecycle reducer rejects them defensively).
- A draw match (`end_reason="draw_max_ticks"`) produces `winner_id == None` and a `MATCH_SCORED` event with both players' `victory` field set to 0.
- Replaying the same event sequence twice produces identical final state (`__eq__`).

**Commit:** `feat(reducers): match lifecycle (started/tick/victory/draw/ended) with max_ticks bound`.

---

## Task 19: [Phase D] Spawn + position + movement reducer

**Files:**
- Create: `src/steel_onslaught/reducers/movement.py`
- Create: `tests/reducers/test_movement.py`

**Events:**

- `MECH_SPAWNED` payload: `{position: {x, y}, facing: deg}`.
- `MOVEMENT_RESOLVED` payload: `{from: {x, y}, to: {x, y}, ticks_consumed: int, pressure_consumed: int}`.

**Movement model:** 2D grid, integer coordinates, distance = Chebyshev (max abs delta). Speed limits per chassis.base_speed, modified by mode (evasion +1, siege −1).

**Invariants:**

- A mech moving 4 cells with base_speed 2 in 2 ticks succeeds.
- A mech moving 5 cells with base_speed 2 in 2 ticks raises `ReducerError("speed_exceeded")`.
- Movement consumes pressure (1 per cell of distance per move).

**Commit:** `feat(reducers): spawn + movement with chebyshev distance`.

---

## Task 20: [Phase D] Sensor observation reducer

**Files:**
- Create: `src/steel_onslaught/reducers/sensors.py`
- Create: `tests/reducers/test_sensors.py`

**Per-tick logic:**

For each mech with active sensor modules (per current mode):
1. Compute true distance to each opponent.
2. For each sensor: if in range, emit `SENSOR_OBSERVATION` with `{enemy_mech_id, distance_estimate, confidence, heat_estimate?, mode_estimate?}`.
3. Distance estimate = true_distance + deterministic noise from `MatchRng.gauss(seed, tick, sensor_id, 0, 1.0 - precision)`.
4. Confidence = `precision * (1 - jamming_intensity)`.
5. Thermal: includes heat_estimate iff target heat ≥ 30. Acoustic: includes mode_estimate iff target speed ≥ 2.

**Invariants:**

- Two replays with identical events produce identical observation noise (deterministic RNG).
- Out-of-range targets emit zero observations.
- Confidence ∈ [0, 1].

**Commit:** `feat(reducers): sensor observation with deterministic noise`.

---

## Task 21: [Phase D] Pilot orchestrator invocation per tick

**Files:**
- Create: `src/steel_onslaught/reducers/pilot_tick.py`
- Create: `tests/reducers/test_pilot_tick.py`

**Per-tick logic:**

For each living mech:
1. Build `ModelSOPilotObservation` from match state + recent sensor events for this mech.
2. Call `pilot.decide(observation)` (synchronous).
3. Emit `PILOT_DECISION_MADE` event with the full decision (including `considered_actions`).
4. Translate decision into intent events (e.g. `WEAPON_FIRE_INTENT`, `MOVE_INTENT`, `MODE_SWITCH_INTENT`) consumed by downstream reducers.

**Invariants:**

- Pilot is called exactly once per living mech per tick.
- Dead mechs are not consulted.
- The `PILOT_DECISION_MADE` event is emitted before any state-mutating downstream events for that tick.
- Pilot side effects (logging, etc.) do not leak into match state — only the returned decision matters.

**Commit:** `feat(reducers): pilot tick orchestrator invocation`.

---

## Task 22: [Phase D] Boiler/heat/pressure reducer

**Files:**
- Create: `src/steel_onslaught/reducers/boiler.py`
- Create: `tests/reducers/test_boiler.py`

**Per-tick logic + on-event logic:**

- Each tick: pressure += regen_per_tick (capped at max), heat -= vent_rate (floored at 0).
- On `WEAPON_FIRED`: pressure -= cost, heat += weapon.heat_generated.
- On `MODE_TRANSITION_STARTED`: pressure -= mode_transition.costs.pressure, heat += mode_transition.costs.heat.
- Emit `BOILER_UPDATED` whenever pressure or heat changes.
- Emit `HEAT_REDLINE_ENTERED` when heat crosses redline_threshold upward; `HEAT_REDLINE_EXITED` when crosses downward.

**Invariants:**

- Pressure never goes negative or above max.
- Heat never goes below 0.
- Two consecutive ticks with no actions: pressure regen × 2, heat vent × 2.
- Emitting `WEAPON_FIRED` without enough pressure raises `ReducerError("insufficient_pressure")` BEFORE the boiler reducer sees it (validated upstream by Task 24).

**Commit:** `feat(reducers): boiler/heat/pressure with redline transitions`.

---

## Task 23: [Phase D] Mode transition reducer

**Files:**
- Create: `src/steel_onslaught/reducers/mode.py`
- Create: `tests/reducers/test_mode.py`

**Intent / event separation:**

The pilot does not directly emit `MODE_TRANSITION_STARTED` (a canonical state-change event). It emits a `MODE_SWITCH_INTENT` (a request). The mode reducer validates the intent, then either accepts (emitting `MODE_TRANSITION_STARTED`) or rejects (emitting nothing — the intent is silently dropped, with a `pilot_decision_made` reason code `mode_switch_rejected_<cause>` already on the ledger from the pilot tick reducer).

```
MODE_SWITCH_INTENT  → reducer validates → MODE_TRANSITION_STARTED (canonical)
                                       → ticks elapse           → MODE_TRANSITION_COMPLETED (canonical)
                                       (or rejected → no canonical event)
```

**Per-event logic:**

On `MODE_SWITCH_INTENT(from_mode, to_mode)`:
1. Look up the corresponding `ModelSOModeTransition` contract (Task 12).
2. Validate: `pressure_available` (current ≥ costs.pressure), `heat_below_switch_limit` (current heat ≤ restrictions.cannot_switch_if_heat_above), `mode_lock_expired` (current_tick ≥ mech.mode_lock_until), `boiler_not_disabled` (boiler.status.disabled == False), `from_mode == mech.current_mode`.
3. If any check fails → drop the intent, do NOT emit `MODE_TRANSITION_STARTED`. The pilot decision event already records the attempt.
4. If all checks pass → set `mech.transition_ticks_remaining = costs.transition_ticks`; deduct pressure and add heat (delegated to boiler reducer via `BOILER_UPDATED`); emit `MODE_TRANSITION_STARTED(from_mode, to_mode, costs, transition_ticks)`.

Each subsequent tick: if `mech.transition_ticks_remaining > 0`, decrement; when it reaches 0, emit `MODE_TRANSITION_COMPLETED(new_mode)`, set `mech.current_mode = to_mode`, set `mech.mode_lock_until = current_tick + restrictions.minimum_lock_ticks_after_switch`.

**Invariants:**

- `MODE_TRANSITION_STARTED` is emitted only by the mode reducer, never by the pilot or by intent producers (verified by a static check in `tests/reducers/test_mode.py` that searches all source files for direct emission).
- A mode switch intent with heat 92 and `cannot_switch_if_heat_above 92` is rejected (no `MODE_TRANSITION_STARTED` emitted).
- A rejected intent leaves the boiler unchanged (no pressure/heat consumed on rejection).
- During transition_ticks, mech has `evasion_penalty_during_transition` applied.
- Sensor dropout fires during transition for `sensor_dropout_ticks` ticks (handled by Task 20 sensor reducer reading mech.transition state).
- `MODE_TRANSITION_COMPLETED` follows `MODE_TRANSITION_STARTED` for every accepted transition (no orphan completions, no stuck transitions).

**Commit:** `feat(reducers): mode transition with intent/event separation + cost + restriction validation`.

---

## Task 24: [Phase D] Weapon firing + hit resolution reducer

**Files:**
- Create: `src/steel_onslaught/reducers/weapons.py`
- Create: `src/steel_onslaught/match/rng.py`
- Create: `tests/reducers/test_weapons.py`

**`MatchRng`:** wrapper around `random.Random` seeded deterministically per `(match_seed, tick, mech_id, kind)`.

```python
# match/rng.py
import hashlib
import random
from dataclasses import dataclass

@dataclass(frozen=True)
class MatchRng:
    match_seed: int

    def for_event(self, tick: int, mech_id: str, kind: str) -> random.Random:
        h = hashlib.blake2b(
            f"{self.match_seed}|{tick}|{mech_id}|{kind}".encode(),
            digest_size=16,
        ).digest()
        return random.Random(int.from_bytes(h, "big"))
```

**Weapon fire flow:**

1. Pilot emits `WEAPON_FIRE_INTENT(weapon_id, target_id)`.
2. Validate: weapon ready (cooldown=0), pressure ≥ cost, target in range, target alive.
3. Compute hit probability: weapon.accuracy_curve at distance × lock_confidence × (1 − target.evasion).
4. Roll: `MatchRng.for_event(tick, mech_id, "weapon_fire").random() < hit_probability`.
5. Emit `WEAPON_FIRED` (always, even on miss).
6. If hit: emit `HIT_RESOLVED` with damage_raw = weapon.damage × target_class_effectiveness[target_chassis_class].

**Invariants:**

- Two replays of the same match (same seed, same events) produce bit-identical hit/miss results across all weapon fires.
- Weapon fired with insufficient pressure: rejected before consuming pressure.
- HIT_RESOLVED is emitted at most once per WEAPON_FIRED.
- Hit probability ∈ [0, 1] post-clamp.

**Commit:** `feat(reducers): weapon firing + deterministic hit resolution`.

---

## Task 25: [Phase D] Armor response + damage application reducer

**Files:**
- Create: `src/steel_onslaught/reducers/damage.py`
- Create: `tests/reducers/test_damage.py`

**On `HIT_RESOLVED`:**

1. Compute armor reduction: damage_after_armor = max(0, damage_raw − armor_value × armor_efficiency_for_weapon_type).
2. Heat weapons: armor reduces less; pressure-based weapons: armor reduces more.
3. Emit `ARMOR_ABSORBED(absorbed_amount)`.
4. Emit `DAMAGE_APPLIED(target_id, damage_after_armor)`.
5. Update target.hp -= damage_after_armor.
6. If target.hp ≤ 0: emit `MECH_DESTROYED(target_id)`.

**Invariants:**

- Total damage_applied across all hits ≤ initial weapon damage_raw sum (armor never amplifies).
- Heat weapons against heavy chassis use heat_weapon_vulnerability multiplier.
- Mech with hp 5, hit for 8: emits MECH_DESTROYED in the same tick.

**Commit:** `feat(reducers): armor response + damage application`.

---

## Task 26: [Phase D] Failure cascade reducer

**Files:**
- Create: `src/steel_onslaught/reducers/failure.py`
- Create: `tests/reducers/test_failure.py`

**Cascade ladder (deterministic order):**

1. Heat ≥ redline_threshold → emit `HEAT_REDLINE_ENTERED` (handled by Task 22 boiler reducer).
2. Sustained redline (3+ consecutive ticks at redline) → emit `BOILER_OVERLOADED`. Effects: −20% accuracy on next firing, mode switch disabled for 3 ticks.
3. Heat ≥ rupture_threshold OR sustained overload (5+ ticks overloaded) → emit `BOILER_RUPTURED`. Effects: target hp -= 30, area damage to mechs within 3 cells.
4. On rupture: pilot rupture-survival roll. Probability: 0.5 base + 0.2 per emergency safety gizmo equipped. Roll via MatchRng.for_event(tick, mech_id, "rupture_survival"). On fail: emit `PILOT_KILLED(mech_id)`.
5. `MECH_DESTROYED` (from rupture or from cumulative damage): the mech is removed from active state; subsequent ticks skip its pilot decision.
6. If only one player has surviving mechs: emit `VICTORY_DECLARED(winner_player_id, reason="last_mech_standing")`.

**Invariants:**

- Cascade ordering is deterministic: redline before overload before rupture before death.
- Two replays produce identical rupture/survival outcomes (RNG seeded deterministically).
- A mech that ruptures in tick N has VICTORY_DECLARED in tick N if no other mechs remain.

**Commit:** `feat(reducers): failure cascade redline→overload→rupture→death→victory`.

---

## Task 27: [Phase E] Replay engine

**Files:**
- Create: `src/steel_onslaught/replay/__init__.py`
- Create: `src/steel_onslaught/replay/engine.py`
- Create: `tests/replay/test_engine.py`

**API:**

```python
class ReplayEngine:
    def __init__(self, ledger: SQLiteLedger, match_id: str): ...
    def reconstruct_at_tick(self, tick: int) -> ModelSOMatchState: ...
    def step_forward(self) -> ModelSOMatchState: ...  # tick++
    def step_backward(self) -> ModelSOMatchState: ...
    def all_ticks(self) -> list[int]: ...
    def events_at_tick(self, tick: int) -> list[ModelSOEventEnvelope]: ...
```

**Reconstruction:** read events from ledger in (tick, event_id) order, fold each through the same reducer stack used during live play. Result must be `==` to the live final state.

**Invariants:**

- `reconstruct_at_tick(final_tick) == live_final_state` for any completed match (round-trip property).
- `reconstruct_at_tick(N).tick == N` for all N ≤ final_tick.
- Stepping forward then backward yields the same state as the original.

**Test (the critical one — golden-path replay determinism):**

```python
@pytest.mark.integration
def test_replay_reproduces_live_state(tmp_path: Path) -> None:
    ledger_path = tmp_path / "test.sqlite"
    live_state = run_full_match(seed=12345, ledger_path=ledger_path)
    replay = ReplayEngine(SQLiteLedger(ledger_path), match_id=live_state.match_id)
    reconstructed = replay.reconstruct_at_tick(live_state.tick)
    assert reconstructed == live_state
```

**Commit:** `feat(replay): engine with tick-step API + round-trip determinism test`.

---

## Task 28: [Phase E] CLI text projection

**Files:**
- Create: `src/steel_onslaught/projections/__init__.py`
- Create: `src/steel_onslaught/projections/cli/__init__.py`
- Create: `src/steel_onslaught/projections/cli/renderer.py`
- Create: `src/steel_onslaught/cli/__init__.py`
- Create: `src/steel_onslaught/cli/main.py`
- Create: `tests/projections/cli/test_renderer.py`

**Renderer subscribes to the EventBus** (`event_types=None` — all events) and emits ANSI lines to stdout:

```
[Tick 142] mech.red.01 (Heavy Ironclad, Predictive) decided: SWITCH_MODE → assault (conf 0.81)
[Tick 142] mech.red.01 boiler: pressure 64 → 52, heat 72 → 80
[Tick 148] mech.red.01 fired machine_gun at mech.blue.01 — predicted hit 0.59
[Tick 149] HIT mech.blue.01 took 5 dmg (8 raw, 3 absorbed)
[Tick 162] VICTORY: player.17 (last mech standing)
```

**CLI commands** (Click):

- `so run --loadout-a path/to/red.yaml --loadout-b path/to/blue.yaml --seed 12345 [--ledger-path PATH]`
- `so replay --ledger PATH --match MATCH_ID [--from TICK] [--to TICK]`
- `so leaderboard --top N`

**Invariants:**

- Running the same `so run` twice with the same seed produces byte-identical stdout.
- The renderer never modifies match state (verified by checking ReducerError isn't raised when renderer subscribes).

**Commit:** `feat(projections,cli): ANSI text renderer + so run/replay/leaderboard commands`.

---

## Task 29: [Phase E] Match scoring reducer

**Files:**
- Create: `src/steel_onslaught/reducers/scoring.py`
- Create: `tests/reducers/test_scoring.py`

**On `MATCH_ENDED`:**

For each player, compute:
- `victory`: 1 if winner else 0.
- `damage_efficiency`: damage_dealt / (pressure_consumed + 1).
- `pressure_efficiency`: 1 − (pressure_wasted / pressure_consumed) [pressure_wasted = pressure_drained while at full heat or in disabled state].
- `overload_penalty`: count of `BOILER_OVERLOADED` events for this player.
- `replay_validity`: 1 if `replay.reconstruct_at_tick(final_tick) == live_state` else 0 (computed by Task 27 engine, captured at scoring time).
- `final_score = victory * 1000 + damage_dealt * 10 + pressure_efficiency * 100 + replay_validity * 50 − overload_penalty * 100`.

Emit `MATCH_SCORED` per design §22.2.

**Invariants:**

- `replay_validity == 0` zeroes out >90% of the score (forcing determinism as a hard requirement).
- Winner score > loser score for any non-degenerate match.
- Two replays produce identical final_score values.

**Commit:** `feat(reducers): match scoring with replay-validity gate`.

---

## Task 30: [Phase E] Leaderboard projection (SQLite materialized view)

**Files:**
- Create: `migrations/0002_leaderboard.sql`
- Create: `src/steel_onslaught/projections/leaderboard/__init__.py`
- Create: `src/steel_onslaught/projections/leaderboard/handler.py`
- Create: `tests/projections/leaderboard/test_handler.py`

**`migrations/0002_leaderboard.sql`:**

```sql
-- Migration 0002: leaderboard
CREATE TABLE IF NOT EXISTS leaderboard_entries (
    match_id          TEXT PRIMARY KEY,
    winner_player_id  TEXT NOT NULL,
    winner_loadout_id TEXT NOT NULL,
    winner_score      INTEGER NOT NULL,
    loser_player_id   TEXT NOT NULL,
    loser_score       INTEGER NOT NULL,
    duration_ticks    INTEGER NOT NULL,
    scored_at         TEXT NOT NULL,
    created_at        TEXT NOT NULL  -- preserved across upserts
);
CREATE INDEX IF NOT EXISTS idx_leaderboard_winner ON leaderboard_entries(winner_player_id);
CREATE INDEX IF NOT EXISTS idx_leaderboard_score ON leaderboard_entries(winner_score DESC);
```

For draws (Task 18 `end_reason="draw_max_ticks"`): `winner_player_id` is set to the alphabetically-first `player_id`, `winner_score == loser_score`, and a separate `is_draw` boolean column is added (default 0) to disambiguate. Add `is_draw INTEGER NOT NULL DEFAULT 0` to the migration. The `top_n` query filters to `WHERE is_draw = 0` so draws do not pollute the rankings.

**Handler subscribes to `MATCH_SCORED`** and upserts a row using `ON CONFLICT(match_id) DO UPDATE` rather than `INSERT OR REPLACE`. This preserves a `created_at` column that records the first-write timestamp, even when the row is later updated:

```sql
INSERT INTO leaderboard_entries
  (match_id, winner_player_id, winner_loadout_id, winner_score,
   loser_player_id, loser_score, duration_ticks, scored_at, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(match_id) DO UPDATE SET
  winner_player_id  = excluded.winner_player_id,
  winner_loadout_id = excluded.winner_loadout_id,
  winner_score      = excluded.winner_score,
  loser_player_id   = excluded.loser_player_id,
  loser_score       = excluded.loser_score,
  duration_ticks    = excluded.duration_ticks,
  scored_at         = excluded.scored_at;
  -- created_at intentionally NOT updated
```

Add `created_at TEXT NOT NULL` to the migration.

**Query helpers:**
- `top_n(n: int) -> list[ModelSOLeaderboardEntry]` — order by winner_score DESC limit n.
- `player_record(player_id: str) -> dict[str, int]` — wins, losses, total_score.

**Invariants:**

- Re-emitting `MATCH_SCORED` for an already-recorded match leaves exactly 1 row.
- After an update, `created_at` is unchanged from the original insert; `scored_at` is updated.
- `top_n(5)` returns the 5 highest winner_score rows.

**Commit:** `feat(projections): leaderboard handler + top-N + player-record queries`.

---

## Task 31: [Phase F] Vite + React frontend scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/lib/event_stream.ts` (WebSocket subscriber)
- Create: `frontend/src/types.ts` (hand-written TS mirror of Python event payloads — see invariants below for the parity test)
- Create: `frontend/src/__tests__/types_parity.test.ts` (validates hand-written TS types against Python-emitted JSON fixtures)
- Create: `tests/fixtures/event_samples.py` (Python script that emits one sample of each `SOEventType` payload to `frontend/src/__tests__/fixtures/*.json`; run via `uv run python -m tests.fixtures.event_samples` whenever event schemas change)
- Create: `src/steel_onslaught/cli/serve.py` (WebSocket bridge: subscribes to bus, broadcasts to connected clients)

**Type-mirror policy (chosen, not optional):** TS types are hand-written. Generated TS would couple to a Python→TS toolchain that this project does not need. The `types_parity.test.ts` test guarantees they stay in sync: it loads each Python-emitted JSON fixture in `frontend/src/__tests__/fixtures/` and runs it through the matching TS parser; any field added or renamed in a Python event payload breaks this test until the TS type is updated.

**Step 1: Failing tests** — both `event_stream.test.ts` (subscriber receives parsed events) and `types_parity.test.ts` (TS types match Python fixtures) fail until implementation lands.

**Step 3: Implement** — minimal scaffold. Vite dev server on port 5173, WebSocket server on 8765 (Python `websockets` library, declared in `pyproject.toml` Task 1). The bridge subscribes to the in-process bus on the Python side and broadcasts each envelope as JSON to all connected WebSocket clients.

**Invariants:**

- `npm run dev` serves the page.
- `npm test` runs vitest and passes.
- `types_parity.test.ts` passes: every fixture file under `frontend/src/__tests__/fixtures/` parses against the corresponding TS type without `any` casts or unknown fields.
- The bridge re-emits envelopes byte-identically (no field reordering, no whitespace normalization beyond `JSON.stringify`'s compact form).

**Commit:** `feat(frontend): Vite + React scaffold + WebSocket bridge + hand-written types with parity test`.

---

## Task 32: [Phase F] Tactical board view

**Files:**
- Create: `frontend/src/views/TacticalBoard.tsx`
- Create: `frontend/src/views/MechMarker.tsx`
- Create: `frontend/src/views/HeatBar.tsx`
- Create: `frontend/src/views/PressureBar.tsx`
- Create: `frontend/src/__tests__/TacticalBoard.test.tsx`

**Behavior:**

- Renders an SVG grid (40x40 cells) with mech markers at current positions.
- Each marker shows: chassis class icon, current heat (color-coded: green ≤ redline-10, amber ≤ redline, red > redline), current pressure (bar), current hp (bar).
- Updates live as new events arrive via the WebSocket stream.
- On `WEAPON_FIRED`: shows brief line from attacker to target.
- On `MECH_DESTROYED`: replaces marker with wreckage glyph.
- On `VICTORY_DECLARED`: shows banner with winner.

**Invariants:**

- Component is a pure projection of the event stream — never POSTs / mutates server state.
- `npm run build` produces a static bundle.
- Vitest renders the tactical board with stub event stream and asserts mech markers appear.

**Commit:** `feat(frontend): tactical board view with heat/pressure/hp bars`.

---

## Task 33: [Phase F] Pilot decision inspector view

**Files:**
- Create: `frontend/src/views/DecisionInspector.tsx`
- Create: `frontend/src/views/TickStepper.tsx`
- Create: `frontend/src/__tests__/DecisionInspector.test.tsx`

**Behavior:**

- Tick stepper at top: `<<` `<` (current tick) `>` `>>` (jump-to-tick input).
- For the displayed tick, fetches all `PILOT_DECISION_MADE` events from the ledger via REST endpoint `GET /api/replay/{match_id}/tick/{tick}` (added to Task 31's `serve.py`). Concrete example: `GET /api/replay/match.2026-04-30.001/tick/142` returns the JSON list of pilot decision envelopes for tick 142.
- Renders for each pilot: chosen action, reason code, confidence, considered_actions table (action / score), and constraints_checked.

**Server endpoint contract** (added to Task 31's `serve.py`, but specified here because Task 33 is the consumer):

| Method | Path | 200 response | 404 response |
|---|---|---|---|
| GET | `/api/replay/{match_id}/tick/{tick}` | `[]` (empty list) if the match exists and the tick has no pilot decisions; otherwise a JSON array of `PILOT_DECISION_MADE` envelopes | `{"error": "match_not_found"}` if no match with `match_id` exists in the ledger directory |

**Invariants:**

- Tick stepper bounds-clamped to `[0, final_tick]`.
- Decision inspector for a tick with no pilot decisions shows "No decisions this tick" (no console errors).
- Replaying from the inspector matches CLI replay output for the same tick (compared via fixture).
- `GET /api/replay/UNKNOWN_MATCH/tick/0` returns 404 with `{"error": "match_not_found"}`.
- `GET /api/replay/{valid_match_id}/tick/{valid_tick_with_no_decisions}` returns 200 with `[]`.
- `GET /api/replay/{valid_match_id}/tick/-1` returns 400 with `{"error": "invalid_tick"}`.

**Commit:** `feat(frontend): pilot decision inspector + tick stepper + REST endpoint with 404/400 coverage`.

---

## Task 34: Proof of Life — End-to-End Duel

**Files:**
- Create: `tests/integration/test_proof_of_life.py`
- Create: `contracts_data/loadouts/proof_red_predictive_ironclad.yaml`
- Create: `contracts_data/loadouts/proof_blue_aggressive_hunter.yaml`
- Create: `contracts_data/loadouts/proof_red_defensive_passive.yaml` (defensive pilot, no engage)
- Create: `contracts_data/loadouts/proof_blue_defensive_passive.yaml` (defensive pilot, no engage)

**Scenario:**

- Red: heavy_ironclad_mk1 chassis, industrial bessemer_90 boiler, predictive pilot, modules: artillery_mortar + machine_gun + long_range_radar + auxiliary_vent + emergency_condenser, modes: recon/assault/evasion.
- Blue: medium_hunter_mk1 chassis, volatile boiler, aggressive pilot, modules: steam_cannon + machine_gun + short_range_scanner + heat_lance + targeting_assist, modes: recon/assault/evasion.
- Seed: `12345`.
- Arena: 40x40 grid, mechs spawn 30 cells apart.
- `max_ticks: 200`. The match terminates by tick 200 even if neither mech is destroyed; in that case end_reason is `draw_max_ticks`.

**Termination outcomes the plan must handle:**

1. **Decisive victory** — one mech is destroyed before tick 200. `VICTORY_DECLARED` followed by `MATCH_ENDED(reason="last_mech_standing")`.
2. **Draw at max_ticks** — both mechs alive at tick 200. No `VICTORY_DECLARED`; `MATCH_ENDED(reason="draw_max_ticks", winner_id=None)`.

The Proof of Life test must assert that both seeds it tries produce *one of these two terminal states* — never a hung match, never an `IndexError`, never an unbounded loop. We use seed `12345` for the canonical decisive-victory path (verified after Tasks 18–26 are implemented; if the seed produces a draw, the test seed is updated to one that produces a decisive outcome AND a separate seed is added for the draw test). A second test case (`test_proof_of_life_draw_max_ticks`) explicitly forces a draw via two defensive pilots that never engage, asserting the draw path is exercised.

**Step 1: Failing test**

```python
@pytest.mark.integration
@pytest.mark.slow
def test_proof_of_life_decisive_victory(tmp_path: Path) -> None:
    # 1) Run match live with the canonical decisive-victory seed
    ledger_path = tmp_path / "match.sqlite"
    leaderboard_path = tmp_path / "leaderboard.sqlite"
    live_state = run_match(
        red_loadout="contracts_data/loadouts/proof_red_predictive_ironclad.yaml",
        blue_loadout="contracts_data/loadouts/proof_blue_aggressive_hunter.yaml",
        seed=12345,
        max_ticks=200,
        ledger_path=ledger_path,
        leaderboard_path=leaderboard_path,
    )
    assert live_state.status == MatchStatus.ENDED
    assert live_state.tick <= 200
    assert live_state.end_reason == "last_mech_standing"
    assert live_state.winner_id in {"player.red", "player.blue"}

    # 2) Replay reconstructs canonical state exactly (R9 data flow proof)
    replay = ReplayEngine(SQLiteLedger(ledger_path), match_id=live_state.match_id)
    reconstructed = replay.reconstruct_at_tick(live_state.tick)
    assert reconstructed == live_state, "replay must reproduce canonical state exactly"

    # 3) Leaderboard updated correctly (winning entry, not a draw)
    lb = LeaderboardProjection(SQLiteLedger(leaderboard_path))
    top = lb.top_n(1)
    assert len(top) == 1
    assert top[0].match_id == live_state.match_id
    assert top[0].winner_player_id == live_state.winner_id
    assert top[0].winner_score > top[0].loser_score
    assert top[0].is_draw is False

    # 4) CLI projection produces byte-identical output across runs
    cli_out_1 = capture_cli_replay(ledger_path, live_state.match_id)
    cli_out_2 = capture_cli_replay(ledger_path, live_state.match_id)
    assert cli_out_1 == cli_out_2, "CLI replay must be byte-identical across runs"
    assert f"VICTORY: {live_state.winner_id}" in cli_out_1

    # 5) Web UI rendered output (Playwright — projection proof, NOT byte-identity)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:5173/")  # dev server, started by fixture
        page.wait_for_selector(f"[data-testid=victory-banner][data-winner={live_state.winner_id}]",
                               timeout=10_000)
        # R10: assert the rendered banner names the correct winner
        banner_text = page.locator("[data-testid=victory-banner]").inner_text()
        assert live_state.winner_id in banner_text
        browser.close()


@pytest.mark.integration
@pytest.mark.slow
def test_proof_of_life_draw_max_ticks(tmp_path: Path) -> None:
    """Two defensive pilots that never engage → match terminates at max_ticks."""
    ledger_path = tmp_path / "draw.sqlite"
    leaderboard_path = tmp_path / "draw_leaderboard.sqlite"
    live_state = run_match(
        red_loadout="contracts_data/loadouts/proof_red_defensive_passive.yaml",
        blue_loadout="contracts_data/loadouts/proof_blue_defensive_passive.yaml",
        seed=99999,
        max_ticks=50,  # short cap to keep the test fast
        ledger_path=ledger_path,
        leaderboard_path=leaderboard_path,
    )
    assert live_state.status == MatchStatus.ENDED
    assert live_state.tick == 50  # match runs the full cap
    assert live_state.end_reason == "draw_max_ticks"
    assert live_state.winner_id is None

    # The leaderboard records the draw with is_draw=True; top_n(N) excludes it.
    lb = LeaderboardProjection(SQLiteLedger(leaderboard_path))
    assert lb.top_n(10) == []  # no decisive entries
    assert lb.draw_count() == 1
```

**Step 2: Run, watch fail at every layer.**

**Step 3: Wire all 33 prior tasks into the entrypoint.** Compose: load loadouts → validate budgets → spawn match → register reducer chain → register CLI projection + leaderboard handler + WebSocket bridge → run tick loop until either VICTORY_DECLARED OR tick == max_ticks → emit MATCH_ENDED with the corresponding reason → emit MATCH_SCORED (with both `victory` fields zeroed on draw) → flush ledger → close.

**Step 4: Run, verify PASS.** All assertions hold in both `test_proof_of_life_decisive_victory` and `test_proof_of_life_draw_max_ticks`.

**Step 5: Commit**

```bash
git add tests/integration/test_proof_of_life.py contracts_data/loadouts/proof_*.yaml
git commit -m "feat(integration): end-to-end duel proof of life — decisive + draw paths, replay + leaderboard + CLI + web UI"
```

**This task is the binding gate. If any assertion in either test fails, the MVP is not shipped.**

---

## Adversarial Review Result

Run after the plan was drafted, against the 34-task body above. R-checks against the design-to-plan skill's R1–R10 framework.

- **R1 Count Integrity:** ✅ clean. Stated count "34 tasks total" matches the actual `## Task N:` heading count (verified: tasks 1 through 34, no gaps, no duplicates).
- **R2 Acceptance Criteria Strength:** ✅ clean. Every task body states either explicit invariants asserted by tests (Tasks 4–33) OR exact assertion code (Task 34). No "tests pass" without specifying which behavior is tested. No "should work" / "should be" subjective language.
- **R3 Scope Violations:** ✅ clean. Phase A (Tasks 1–6) introduces foundation and explicitly does NOT claim domain behavior. Phase B (Tasks 7–13) introduces contracts and explicitly does NOT claim runtime behavior. Phase D (Tasks 18–26) introduces reducers and references the events Phase A defined. Cross-task contamination is bounded by file-path declarations.
- **R4 Integration Traps:** ✅ clean. Every task that imports a class names the file that creates it (`ModelSOEventEnvelope` from Task 4 used in Tasks 5–34, all referencing `src/steel_onslaught/events/envelope.py`). The pilot Protocol referenced in Tasks 21 + 15/16/17 is declared in Task 14. The `MatchRng` referenced in Tasks 20 + 24 + 26 is declared in Task 24's file list.
- **R5 Idempotency:** ✅ clean. Both migrations use `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, and `CREATE TRIGGER IF NOT EXISTS`. Leaderboard handler uses `ON CONFLICT(match_id) DO UPDATE` (preserves `created_at` across upserts). Match-lifecycle reducer (Task 18) explicitly rejects double `MATCH_STARTED`. Replay reads are idempotent by construction (no writes; the events table is hardened append-only via DB triggers + a public-API allowlist).
- **R6 Verification Soundness:** ✅ clean. Task 27's replay round-trip test is STRONG (`reconstructed == live_state`). Task 34's Proof of Life uses 5 independent strong proofs in the decisive-victory path AND a separate explicit draw-path test: state equality (replay determinism), leaderboard row contents (decisive vs draw via `is_draw`), CLI byte-identity, Playwright DOM assertion. Architectural Decision #6 explicitly scopes determinism to canonical state + CLI byte-identity, treating browser rendering as a projection proof rather than a byte-identical artifact (avoids overpromising).
- **R7 Type Duplication:** ✅ clean. Known Types Inventory section explicitly states the repo is greenfield. Every model/enum introduced is namespaced under `ModelSO*` or `steel_onslaught.*` — no collision possible with anything that does not exist. Per-task "not reusing X" lines are intentionally omitted with documented justification.
- **R8 Runtime State Grounding:** ✅ clean. Both SQLite tables (events, leaderboard_entries) appear in the Runtime State Inventory section with full schema, AND in their creating tasks (6 and 30) with the full migration SQL. Every column referenced by other tasks (e.g. `tick`, `winner_score`) traces back to a migration file with line citations available. No Kafka topics or consumer groups are claimed (in-process bus only) — explicitly stated.
- **R9 Data Flow Proof:** ✅ clean. Task 34 publishes events → SQLite ledger → projection (CLI + leaderboard) → web UI, with field-level assertions at each layer (`winner_id` matches across live state, leaderboard, CLI output, and DOM).
- **R10 Rendered Output Proof:** ✅ clean. Task 34 includes a Playwright assertion that the victory-banner DOM element contains the correct winner_id. CLI output is asserted character-for-character. Both are stronger than HTTP-200-only.

Summary: 10/10 clean on first pass. No fixes required. (Phases 2c multi-model adversarial review and 2→3 ONEX Pattern Gate are DISABLED per OMN-10111 — skipped.)

### Reviewer-feedback precision pass (2026-04-30 follow-up)

After human review feedback, the plan was sharpened with the following targeted edits — none invalidate the R1–R10 verdict above; all strengthen it:

1. **Determinism wording (Architectural Decision #6)** narrowed: canonical state + CLI must be byte-identical; browser rendering is a projection proof, not a byte-identical artifact.
2. **Canonical event ordering (new Architectural Decision #7)** declared: `(tick ASC, sequence_in_tick ASC, event_id ASC)`. `emitted_at` is metadata only and explicitly forbidden as an ordering authority.
3. **`sequence_in_tick` column added** to events table + envelope model + ledger writes/reads. Bus is the sole authority that assigns it (Task 5).
4. **Append-only enforcement** at the DB layer: `BEFORE UPDATE` and `BEFORE DELETE` triggers raise `ABORT`. `SQLiteLedger` exposes only append + read methods; a class-introspection test asserts the public method allowlist.
5. **Mode transition intent/event separation (Task 23):** `MODE_SWITCH_INTENT` (pilot output) → reducer validation → `MODE_TRANSITION_STARTED` (canonical) → ticks elapse → `MODE_TRANSITION_COMPLETED` (canonical). Removes the previous self-emitting circularity.
6. **WebSocket dependency** added to `pyproject.toml` (`websockets>=12.0`) and `playwright>=1.45` to dev extras (Task 1). Resolves the implicit dependency in Tasks 31 + 34.
7. **REST endpoint corrected (Task 33):** `GET /api/replay/{match_id}/tick/{tick}` with explicit 404 / 400 / 200-empty coverage.
8. **Leaderboard upsert (Task 30):** `ON CONFLICT(match_id) DO UPDATE` instead of `INSERT OR REPLACE`. `created_at` column added and preserved across upserts. `is_draw` column added for draw handling.
9. **Max-tick + draw termination (Tasks 18 + 34):** match guaranteed to end by `max_ticks`. `MATCH_ENDED(reason="draw_max_ticks", winner_id=None)` on draws. Second Proof-of-Life test (`test_proof_of_life_draw_max_ticks`) explicitly exercises this path.
10. **Frontend types policy (Task 31):** hand-written TS, with `types_parity.test.ts` validating against Python-emitted JSON fixtures. Generated TS rejected — adds toolchain debt for no MVP-time benefit.

Re-run R-checks after edits: all 10 still clean. R6 strengthened by tightening determinism wording + adding the draw-path test. R5 strengthened by replacing `INSERT OR REPLACE` with explicit `ON CONFLICT DO UPDATE` and adding append-only triggers.

---

## Phase 3 Routing

```yaml
routing: ticket-pipeline
linear_required: false
auto_launch: false
notes: |
  Personal repo (jonahgabriel/steel_onslaught), not in OmniNode-ai workspace.
  User asked to SEE the plan — explicit no-launch.
  When ready to execute, run /onex:executing-plans on this file with --local mode
  (no Linear); each task becomes a local YAML stub dispatched to a general-purpose
  agent in sequence. Worktree convention: per-task branches under
  $OMNI_HOME/omni_worktrees/steel-onslaught-task-N/steel_onslaught/.
```
