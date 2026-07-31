# Hermetic battery snapshot recipe — OMN-15265

Frozen, pinned execution environment for a long-running battery, so a
concurrent session's `pull-all.sh` / merge activity against the canonical
`$OMNI_HOME` clones can no longer touch a running battery at all. Built and
proven live for the OMN-15172 acceptance run's attempt #3
(`~/.omnibase/battery_envs/omn15172-hermetic-20260727/`) after the same
`OMN-14060` drift class killed attempts #1 and #2 -- see
[`OMN-15265`](https://linear.app/omninode/issue/OMN-15265) for the incident
history this recipe closes.

**This recipe is a hedge against `$OMNI_HOME`-clone churn from OTHER
sessions, not a substitute for `scripts/run_display_salience_battery.py`'s
own belts** (`_preflight_delegation_cli`, OMN-15240; `_drift_recheck`,
OMN-15265, this same ticket) -- run both together. This recipe does not
protect against every other lane also mutating `$OMNI_HOME`; it only
removes the SHARED-CLONE hazard for the battery's own environment.

## When to use this

Any battery expected to run for hours against seeds that are expensive to
re-run (the whole point of a battery's contamination discipline is that a
dead seed cannot be silently re-attempted) AND that shares a machine with
other active sessions that pull/merge into the same canonical
`$OMNI_HOME/{omnimarket,omnibase_infra}` clones. A short smoke run (a few
seeds, minutes) does not need this -- the launch-time preflight
(`_preflight_delegation_cli`) and the mid-run belt (`_drift_recheck`) are
enough there.

## 1. Pinned fresh clones

Clone the three repos the battery touches into a dedicated snapshot root,
each pinned to an exact commit -- never a branch head
(`reference_never_pin_a_feature_branch_head`):

```bash
SNAP=~/.omnibase/battery_envs/<slug>-$(date +%Y%m%d)
mkdir -p "$SNAP"

git clone https://github.com/OmniNode-ai/omnimarket.git "$SNAP/omnimarket"
git -C "$SNAP/omnimarket" checkout <omnimarket_sha>

git clone https://github.com/OmniNode-ai/omnibase_infra.git "$SNAP/omnibase_infra"
git -C "$SNAP/omnibase_infra" checkout <omnibase_infra_sha>

git clone https://github.com/jonahgabriel/steel_onslaught.git "$SNAP/steel_onslaught"
git -C "$SNAP/steel_onslaught" checkout <steel_sha>
```

The snapshot root is deliberately laid out with the same sibling structure
as the real `$OMNI_HOME` (`omnimarket/`, `omnibase_infra/`,
`steel_onslaught/` as siblings) -- that is what makes step 3's `OMNI_HOME`
redirect transparent to every `$OMNI_HOME`-relative resolution in both the
battery driver and the drift guard.

**Live-proven pins** (OMN-15172 acceptance attempt #3, 2026-07-27):
`omnimarket@f6979df8a5`, `omnibase_infra@b1bda5967c`,
`steel_onslaught@985ca70c6c`.

## 2. Dedicated venvs per snapshot

```bash
cd "$SNAP/omnibase_infra" && uv sync
cd "$SNAP/steel_onslaught" && uv sync --extra live
```

Each snapshot gets its own `.venv` -- never reuse the canonical clones'
venvs. This is what makes the venv itself immune to a concurrent
`pull-all.sh --repair` or `install-node-skill-package.sh` re-run against
the LIVE canonical clones.

**Step 2 alone does NOT produce a usable `omnibase_infra` venv. Step 3 is
mandatory, not optional polish.** `omnimarket` is deliberately not a declared
`omnibase_infra` dependency (repo layering is compat -> core -> spi -> infra and
`omnimarket` sits ABOVE infra, so declaring it would invert the layer graph --
see the header of `scripts/install-node-skill-package.sh`, OMN-13829). It is a
runtime-composed provider discovered through `onex.nodes` entry-points, so
`uv sync` leaves it **absent from the infra venv entirely** -- verified live in
`venv.log`, where the first `uv sync` installs 195 packages and `omnimarket` is
not among them. The delegation CLI's drift guard then hard-fails at the first
LLM call with:

```
omnimarket is NOT INSTALLED from git in this interpreter
```

which surfaces to the battery driver as an `LlmTransportError` and aborts the
run. This is a snapshot-procedure failure, not a code defect -- it killed the
OMN-15488 canary at 2026-07-30T18:59:12Z, after a runner that had built venvs
per §2 and skipped §3.

## 3. Mandatory: pinned VCS co-install of `omnimarket` (`--no-deps`)

Inside the frozen `omnibase_infra` clone, co-install the SAME pinned
`omnimarket` commit -- never the dynamically-resolved default (which would
resolve against the live canonical clone / a live `git ls-remote`, reintroducing
exactly the drift this recipe exists to remove):

```bash
cd "$SNAP/omnibase_infra"
OMNIMARKET_REF=<omnimarket_sha> scripts/install-node-skill-package.sh --execute
```

That script is the canonical mechanism and it already does the right thing
internally: `uv pip install --no-deps "omnimarket @ git+...@$OMNIMARKET_REF"`
plus its pinned omni-internal leaf deps. If you are scripting the snapshot
build yourself rather than shelling out to it, the minimal equivalent -- proven
live on OMN-15488 attempts 3 and 4 and the full 61-match battery -- is:

```bash
cd "$SNAP/omnibase_infra"
env -u PYTHONPATH uv pip install --python .venv/bin/python --no-deps \
  "omnimarket @ git+https://github.com/OmniNode-ai/omnimarket.git@<omnimarket_sha>"
```

`--no-deps` is load-bearing, not an optimization. The dependency closure is
already supplied by step 2's `uv sync`; what `--no-deps` buys is skipping a
transitive resolve that **cannot succeed**. A plain resolving
`uv pip install "omnimarket @ git+...@<sha>"` fails deterministically, before
any verification step can even run, because `omninode-memory` (pulled in
transitively by `omnimarket`) declares two different `omnibase_infra`
git-commit URLs:

```
× Failed to resolve dependencies for `omninode-memory` (v0.17.0)
╰─▶ Requirements contain conflicting URLs for package `omnibase-infra`:
    - git+https://github.com/OmniNode-ai/omnibase_infra.git@00e5a02a...
    - git+https://github.com/OmniNode-ai/omnibase_infra.git@77144f83...
  help: `omninode-memory` (v0.17.0) was included because `omnimarket` (v0.4.3)
        depends on `omninode-memory`
```

uv exits 1, and a `set -euo pipefail` snapshot script aborts mid-build. This is
the second of the two runner failure classes (OMN-15488 attempt 2, reproduced
twice at 2026-07-30T19:01:50Z and 19:03:24Z). Do not "fix" the first failure
class by reaching for a full-resolve install -- that is exactly the trap.

### Ordering and idempotence

The VCS install must come AFTER `uv sync`, and any LATER `uv sync` against the
infra venv **uninstalls it again**. `omnimarket` is not in that project's
lockfile, so `uv sync` prunes it -- visible verbatim in `venv.log` as
`- omnimarket==0.4.3 (from git+...)` immediately after a re-sync. A snapshot
script that re-runs its phase-1 checkout+resync (the idempotent
re-pin path used for OMN-15488 attempt 4) MUST re-run this install every time,
and re-verify, not assume the earlier install survived.

### Verification is the real gate

Never trust the installer's exit code alone -- assert on `direct_url.json`:

```bash
python3 - <<'PY'
import glob, json, os, sys
pin = os.environ["OMNIMARKET_SHA"]
snap = os.environ["SNAP"]
hits = glob.glob(f"{snap}/omnibase_infra/.venv/lib/python3.*/site-packages/omnimarket-*.dist-info/direct_url.json")
if not hits:
    sys.exit("FAIL: omnimarket not installed in the snapshot infra venv")
info = json.load(open(hits[0]))
vcs = info.get("vcs_info", {})
if vcs.get("vcs") != "git" or vcs.get("commit_id") != pin:
    sys.exit(f"FAIL: expected vcs=git commit_id={pin}, got {info}")
print(f"OK: omnimarket VCS-pinned @ {pin} verified")
PY
```

A passing read looks like:

```json
{"url": "https://github.com/OmniNode-ai/omnimarket.git",
 "vcs_info": {"vcs": "git", "commit_id": "<omnimarket_sha>",
              "requested_revision": "<omnimarket_sha>"}}
```

Both halves matter: `vcs == "git"` is what the drift guard checks (a plain
non-VCS install passes an "is it installed" test and still fails the guard), and
`commit_id == <omnimarket_sha>` is what makes the snapshot hermetic. Log the
verified line into the runner log so a later reader can tell a good snapshot
build from a bare `uv sync` one at a glance -- the OMN-15488 runner emits
`snapshot: done (omnimarket VCS-pinned @ <sha> verified)`, and its plain
`snapshot: done` predecessor is precisely the build that failed.

## 4. `OMNI_HOME` redirect at launch

Every battery-driver invocation gets `OMNI_HOME` REDIRECTED to the snapshot
root, never the real workspace root, plus `PYTHONPATH` explicitly cleared
(`reference_pythonpath_shadows_worktree_source` -- an inherited
`PYTHONPATH` pointing at the real canonical clones would silently shadow
the frozen snapshot's own `src/`, defeating the whole point):

```bash
cd "$SNAP/steel_onslaught"
env -u PYTHONPATH OMNI_HOME="$SNAP" \
  uv run python scripts/run_display_salience_battery.py \
    --corner default --n 30 --seed-base 5000 --max-ticks 1000 --fresh \
    --state-root "$SNAP/battery_state/<run>/default"
```

This fragment shows the env redirect **only**. Do not launch a real battery
this way: the actual launch wraps the same driver invocation in the
supervised entrypoint of §5, which is what makes a crash or a stall report
itself.

Because `OMNI_HOME=$SNAP`, `_drift_recheck`'s belt (this ticket) compares
the frozen snapshot's OWN `omnimarket` install against the frozen
snapshot's OWN `$OMNI_HOME/omnimarket` clone HEAD -- both sides of the
comparison are pinned and stable, so the belt reads clean for the entire
run, exactly as it should. Nothing about running inside a snapshot
disables the belt; it simply never has anything to catch there, because
nothing in the frozen tree can drift.

## 5. Launch discipline: one supervised entrypoint (OMN-15588)

Every battery is launched through `so battery-watch`, which supervises the
driver, watches its progress, sequences the next corner, and -- the part no
earlier arrangement could do -- **actively reports how the run ended**:

```bash
export STEEL_BATTERY_NOTIFY_COMMAND="<argv that reaches you; outcome JSON on stdin>"
# and/or: export STEEL_BATTERY_NOTIFY_WEBHOOK="<chat-compatible webhook URL>"

nohup env -u PYTHONPATH OMNI_HOME="$SNAP" uv run so battery-watch \
  --run-id "<run>-default" \
  --raw-path "$SNAP/battery_state/<run>/default/battery_raw.jsonl" \
  --log-path "$SNAP/battery_state/<run>/default.log" \
  --expected-rows 30 \
  --stall-deadline-seconds 3600 \
  -- \
  uv run python scripts/run_display_salience_battery.py --corner default --n 30 \
    --seed-base 5000 --max-ticks 1000 --fresh \
    --state-root "$SNAP/battery_state/<run>/default" \
  </dev/null > "$SNAP/battery_state/<run>/watchdog.log" 2>&1 &
disown
```

At least one notification channel is **mandatory**: with neither env var set,
`battery-watch` exits 4 and never launches the driver. That refusal is the
mechanism -- a battery whose only failure signal is a file on disk cannot be
started through this path at all.

`</dev/null` on stdin -- an inherited terminal stdin has repeatedly caused
double-launch races on this program (a background process that blocks on
stdin can be woken by an unrelated keystroke in the parent shell). Before
ANY relaunch of the same corner, check the process is not already running:

```bash
pgrep -f "run_display_salience_battery.py --corner default"
```

A relaunch against a `--state-root` an existing process still owns is a
silent data race on `battery_raw.jsonl`/`events.sqlite3` -- `pgrep` first,
every time.

## 6. Terminal states, and sequencing corners unattended

`battery-watch` reports exactly one terminal state per run and exits on it:

| State | Meaning | Exit |
|---|---|---|
| `COMPLETED` | driver exited 0 with `--expected-rows` rows | 0 |
| `INCOMPLETE` | driver exited 0 but **short** -- follow-on work withheld | 2 |
| `CRASHED` | driver exited nonzero; the notification carries the log tail | 1 |
| `STALLED` | no new row within `--stall-deadline-seconds`; driver terminated | 1 |
| (any) | no channel accepted the outcome -- nobody was told | 3 |

`STALLED` is the case the previous hand-rolled watcher could not detect at
all: it polled for process *absence*, so a driver that hung while still
resident was invisible to it for as long as it stayed alive. Progress is
measured from `battery_raw.jsonl` (one row per completed seed), so a slow
battery is never mistaken for a wedged one.

To sequence corners, pass the next launch to `--on-complete-exec`. It fires
**only** on `COMPLETED`, which is the same fail-closed gate the old
`NEEDS_ATTENTION` sentinel implemented -- except an incomplete prior corner
now pushes a notification instead of waiting to be noticed:

```bash
  --on-complete-exec "env -u PYTHONPATH OMNI_HOME=$SNAP uv run so battery-watch \
     --run-id <run>-prominent \
     --raw-path $ROOT/prominent/battery_raw.jsonl \
     --log-path $ROOT/prominent.log --expected-rows 30 \
     -- uv run python scripts/run_display_salience_battery.py --corner prominent \
        --n 30 --seed-base 5000 --max-ticks 1000 --fresh --state-root $ROOT/prominent"
```

**Do not reintroduce a `BATTERY_DONE` / `NEEDS_ATTENTION` shell wrapper.** On
the OMN-15488 run an attempt-1 crash sat undetected for roughly five hours
behind a correctly-written sentinel that nobody read.
`tests/battery/test_watchdog.py` reads this file and fails if the bash
sentinel recipe returns to it.

## Lesson: in-process gate, never the fetch-based shell script

`scripts/check-omnimarket-venv-drift.sh` does a live `git fetch` against
the remote and compares against the FETCHED ref. Run it (or anything that
does a live fetch/`ls-remote`) against a hermetic snapshot and it
**false-positives** -- the whole point of the snapshot is that it stays
pinned behind the remote for the run's duration, and a fetch-based check
reads that as drift.

`omnibase_infra.cli.omnimarket_drift_guard.check_omnimarket_drift` (the
function `_drift_recheck`, this ticket, wires into the driver's own
mid-run belt) is LOCAL-only by construction -- it compares the current
interpreter's installed `omnimarket` commit against a LOCAL
`git rev-parse HEAD` on `$OMNI_HOME/omnimarket`, never a network call. Point
it at a hermetic snapshot's `$OMNI_HOME` and it reads clean for the whole
run, because both sides of the comparison are the same pinned, unmoving
commit. Use the in-process gate for anything that runs inside a snapshot;
reserve the fetch-based shell script for interactive sessions against the
LIVE canonical clones, where knowing about upstream drift you have not yet
pulled is exactly the point.

## Evidence

- [`OMN-15265`](https://linear.app/omninode/issue/OMN-15265) -- the ticket
  this recipe and the driver-side belt (`_drift_recheck`) close.
- `docs/tracking/ROLLING_WORK_LEDGER.md` (omni_home), 2026-07-27T20:45Z
  entry -- hermetic snapshot build + smoke proof, live-observed shared-clone
  race (`omnibase_infra` moved `b1bda596` -> `7d069f3d` under a concurrent
  session mid-build, the exact hazard this recipe removes for the battery
  itself).
- `~/.omnibase/battery_envs/omn15172-hermetic-20260727/` -- the live
  snapshot this recipe was extracted from (pins, `chain_prominent.sh`,
  `chain.log`, `smoke_run.log`). Read-only reference; do not mutate a
  running battery's snapshot.
- [`OMN-15582`](https://linear.app/omninode/issue/OMN-15582) -- the ticket
  the §2/§3 VCS-install amendment closes. Both runner failure classes were
  found live during the OMN-15488 battery launch on 2026-07-30 and each cost
  a launch attempt:
  - attempt 1, `ROLLING_WORK_LEDGER.md` 2026-07-30T18:59:12Z -- venvs built
    per §2 only, §3 skipped; canary aborted at the first LLM call with
    `omnimarket is NOT INSTALLED from git in this interpreter`.
  - attempt 2, ledger 2026-07-30T19:03:48Z -- the runner's own improvised fix
    used a full-resolve `uv pip install`; uv exited 1 on the
    `omninode-memory` conflicting-URL error (reproduced twice) and the
    snapshot script aborted before verification.
  - attempt 3 onward, `runner.log` 2026-07-30T19:06:03Z --
    `snapshot: done (omnimarket VCS-pinned @ f6979df8a5... verified)` after
    switching to the `--no-deps` VCS install; attempt 4 (ledger
    2026-07-30T20:32:05Z) carried the same snapshot to canary PASS and the
    full 61-match battery.
  - `~/.omnibase/battery_envs/omn15488-hermetic-20260730/battery_state/logs/`
    (`runner.log`, `venv.log`) -- the raw uv output quoted in §3, including
    the `- omnimarket==0.4.3 (from git+...)` prune line that proves a later
    `uv sync` undoes the install.
