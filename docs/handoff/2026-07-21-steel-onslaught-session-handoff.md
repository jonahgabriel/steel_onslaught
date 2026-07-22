# Steel Onslaught — Session Handoff (2026-07-21)

Repo: `jonahgabriel/steel_onslaught` · default branch `main` · conventional-commit titles, no ticket prefix.
CI installs Playwright chromium and runs it; **CI green is required**. Locally chromium is absent, so
`tests/…/test_proof_of_life.py` fails **local-only** (deselected/skipped locally, passes in CI).

All PR / CI / SHA facts below were read live via `gh` on 2026-07-21 — not transcribed. Every open PR was
checked with `gh pr checks <n>`; main's CI via the commit check-runs API.

---

## 1. State of the world

Steel Onslaught is a browser-rendered, LLM-piloted tactical mech skirmish: two AI pilots ("mechs") program
and resolve moves on a hex/grid arena, with all live decisions made by real language models (LLM-only — no
scripted/deterministic pilot on the live path). As of this session it **launches keyless** (`uv run so play`,
zero flags) and **truly plays on live Qwen** (`Qwen3.6-35B-A3B` over Tailscale `http://omninode-pc.tail75df5e.ts.net:8000`)
on a 60×60 `foundry_60` board with **two visibly distinct AI pilots** — RED Qwen berserker scout (spawn 4,4)
vs BLUE Qwen sniper ironclad (spawn 55,55), split decks M3/W2 vs M2/W3. It is, however, **not yet a
watchable match**: the top defect is a **mid-match stall** — one Qwen plan the engine rejects as
`invalid_action_parameters` freezes the game at that tick with no retry, no terminate, no recovery — and the
**brawler-vs-sniper balance is broken** (the short-range berserker gets chunked by artillery on approach,
fires 0 shots / 17 out-of-range rejects; 160-HP ironclad vs 60-HP scout reads unfair; ~31 ticks in ~16s then
freeze is a burst, not a match). The stall has a complete, CI-verified fix on open **PR #115**; the balance
work is not started.

---

## 2. Live-GH scorecard (read live 2026-07-21)

**`main` @ `f869d6a6bf9d21d7b627276d9e22f0b50fd5d1df`** — CI: `python-test` ✅ · `sanitize-text` ✅ ·
`frontend-test` ✅ · `evidence-schema` ✅ (all `success`).

Open PRs (`gh pr list --state open`), each with its four checks (`gh pr checks`):

| PR | Title | head SHA | mergeable | CI (evidence-schema / frontend-test / python-test / sanitize-text) |
|----|-------|----------|-----------|-------------------------------------------------------------------|
| #115 | fix(match): recover live-provider semantic stall with bounded reprompt + classified terminal | `f6797bb` | MERGEABLE | ✅ / ✅ / ✅ (3m12s, full suite incl. Playwright) / ✅ — **all 4 pass** |
| #114 | feat(pilots): human-editable mech prompts and plug-in rule handlers | `1cddd1c` | MERGEABLE | ✅ / ✅ / ✅ / ✅ — all 4 pass |
| #113 | feat(play): one-command launch and reliable start lifecycle | `aca2afd` | MERGEABLE | ✅ / ✅ / ✅ / ✅ — all 4 pass |
| #112 | feat(catalog): every configured model selectable for either seat | `127b40a` | MERGEABLE | ✅ / ✅ / ✅ / ✅ — all 4 pass |
| #108 | docs: Steel Onslaught finish plan + Phase 2.5 design + audit (this handoff rides here) | `bf9bea6` | MERGEABLE | ✅ / ✅ / ✅ / ✅ — all 4 pass |
| #100 | feat(range): add preferred-range policy handler and metrics — **SUPERSEDED by #114** | `672d56a` | **UNKNOWN** | ✅ / ✅ / ✅ / ✅ — all 4 pass |
| #81 | feat(cards): guarantee movement variety via opt-in rule — **SUPERSEDED by #114** | `f1c998e` | **UNKNOWN** | ✅ / ✅ / ✅ / ✅ — all 4 pass |

**Findings from the scorecard:**
- **No red CI on any open PR and none on `main`.** All 7 open PRs are 4/4 green; main is 4/4 green.
- **Hard finding — #100 and #81 report `mergeable: UNKNOWN`.** GitHub has not computed mergeability for
  either (they are stale/superseded and never rebased onto current `main`). CI-green does not mean
  conflict-free here — treat both as likely-conflicting-if-landed. They are superseded by #114 and should be
  **closed, not merged** (see decisions §4d). Do not land either.
- Merged PRs from this session (#109/#110/#111) are all `MERGED`; #109's merge commit **is** current
  `main` head `f869d6a`.

---

## 3. What was accomplished this session (with honest proof class)

**Merged to `main`** (in merge order — verified `MERGED` via `gh pr view`):
- **#111** `fix(match): correct every wrong or missing match terminal` — merge `1b8ac8f`, 21:03Z. Terminal
  correctness. **Proof: merged + CI-green (seam/test-verified).**
- **#110** `fix(seat-identity): one validated seat contract + LLM-only live decisions` — merge `05fd8ae`,
  21:07Z. Seat identity (distinct pilots) + LLM-only guarantee on the live path. **Proof: merged +
  CI-green, AND live-verified** — the two distinct pilots rendered correctly in the real browser run below.
- **#109** `feat(ui): render the card-cadence pilot reasoning in the deck` — merge `f869d6a` (= main head),
  21:10Z. Reasoning visibility. **Proof: merged + CI-green (seam-verified).**

**Open feature PRs (built + CI-green this session, NOT yet on `main`):**
- **#115** — the stall fix (see below). **Proof: live-verified + mutation-proven** (highest-confidence PR).
- **#114** — human-editable mech prompts + plug-in rule handlers (browser prompt/rules workbench).
  **Proof: seam/CI-verified. Caveat: the workbench UI was built but NOT mounted in `App.tsx`** — see §4c.
- **#113** — one-command launch + reliable start lifecycle. **Proof: seam/CI-verified** (the keyless launch
  it hardens WAS exercised live).
- **#112** — every configured model selectable for either seat. **Proof: seam/CI-verified.**

**#115 stall fix — the headline deliverable (live-verified + mutation-proven):**
Root cause: `MatchRunner.run` caught only `LlmCompletionBoundaryError`; a semantic parse failure
(`LlmSemanticError`, a `ValueError`, not an `LlmTransportError`) sailed past that handler and propagated out
of `run()` with **no `MATCH_ENDED`** emitted — the tick-31 freeze — and with **no retry** (one bad plan
killed the match). Fix: on the live `raise` policy the semantic error now routes to a **bounded same-model
reprompt** (3 total real completions: 1 initial + 2 repairs, each with its own `llm_completion_failed`
evidence and the sanitized rejection annotated in the repair prompt); on exhaustion it raises the new
`LlmSemanticExhaustedError(LlmTransportError)`, which the runner converts into a **classified
`MATCH_ENDED reason=provider_semantic_failure`** terminal. No deterministic-pilot substitute was introduced
on the live path (the LLM-only guarantee holds; the deterministic fallback is reachable only under the
opt-in `fallback` policy). The stall was **proven to reproduce without the fix** (hermetic run vs
`origin/main`: 1 provider call, no retry, `MATCH_ENDED` absent) and **mutation-tested** (removing the
terminate-on-exhaustion handler turned the regression test RED with an uncaught exception and no terminal —
proving retry and terminate are independently load-bearing). Adversarially verified: PASS.

**Docs (on #108, this branch `docs/so-finish-plan`):** the finish plan
(`docs/plans/2026-07-21-steel-onslaught-finish-plan.md`) with a **Phase 2.5 design** (objectives-based
victory + Heavy/Assault weapon keywords), the finish audit
(`docs/2026-07-21-steel-onslaught-finish-audit.md` + `…-findings.json`), and a **new live-run subsection**
recording verified gameplay. **Proof: docs, backed by the live run below.**

**Live-run verification (real browser, screenshots committed):**
- WORKS: keyless `uv run so play`; live Qwen `Qwen3.6-35B-A3B`; 60×60 `foundry_60` renders with terrain;
  two distinct pilots (RED berserker vs BLUE sniper — the #110 seat-identity fix renders correctly); split
  decks visibly M3/W2 vs M2/W3; `llm_completion_requested` ×14 / `resolved` ×13; real play
  (`movement_resolved` ×30, blue `artillery_mortar` fired ×3, one 34-damage hit put red to HP 26/60). The
  reported "setup/PLAYER SELECT panel doesn't disappear on start" bug did **NOT** reproduce.
- BROKEN (observed live): the **tick-31 `invalid_action_parameters` STALL, no terminal** (fixed by #115);
  the **brawler never brawled** (RED fired 0 shots, `weapon_fire_rejected` ×17 out-of-range — chunked on
  approach, never closed); **HP asymmetry** (blue 160 vs red 60 reads unfair); **pacing** (~16s burst then
  freeze). Screenshots: `docs/evidence/2026-07-21-live-run/{02-configured,03-just-started,04-running}.png`.

---

## 4. Pending decisions (operator)

**a. Which overlay is THE demo?** There is **no default overlay anywhere** — every entrypoint declares one
explicitly. A true split-deck match IS reachable (blue actually programs a distinct sniper deck), but only
by passing the split overlay explicitly as `--overlay`; nothing routes to it by default, and the
`--catalog-index configured_v1.yaml` path (which merges all five providers live) is single-deck. **Decide:
wire the split overlay as the default demo, or accept the reachable single-deck path as the demo.** The
split overlay is real, unreferenced, and stranded until this is decided.

**b. Zero-config default provider — GLM (needs a key) vs keyless Qwen?** Out of the box the browser
demo's catalog default (`configured_v1.yaml` → `live_glm_cards.yaml`) is **GLM 5.2 over `api.z.ai`**, which
requires `LLM_GLM_API_KEY` — while the keyless `uv run so play` path runs live on local Qwen with no
secret. **Decide: flip the zero-config default to keyless Qwen** (so the demo runs with zero setup), or keep
GLM as the catalog default and document the key requirement. Today the two "defaults" disagree.

**c. Mount the browser prompt/rules workbench?** #114 built the human-editable prompt + plug-in-rule
workbench UI but **`App.tsx` does not mount it** — the feature ships dark. **Decide: mount the workbench in
`App.tsx` as part of landing #114** (recommended — otherwise the PR lands dead UI), or defer mounting.

**d. Close the superseded PRs?** #81 (movement-variety) and #100 (preferred-range) are **superseded by
#114** and both show `mergeable: UNKNOWN` (never rebased). **Decide: close #81 and #100** rather than
rebasing/merging them.

---

## 5. Next actions (priority order)

1. **Land the stall fix (#115).** It is live-verified + mutation-proven, MERGEABLE, 4/4 CI green. This
   retires the #1 blocker (mid-match freeze). Land first, independent of the others.
2. **Coordinated merge-and-mount pass for #113 + #112 + #114.** They share seams (`application.ts`,
   `main.py`), so **land them together** to avoid seam drift, and in the same pass: **mount the prompt/rules
   workbench in `App.tsx`** (§4c), **flip the zero-config default to keyless Qwen** (§4b), and **close the
   superseded #81 and #100** (§4d). Decide the demo overlay (§4a) here too since it touches the same launch
   path.
3. **Game-DEPTH tranche (not started — real gameplay work, not wiring):**
   - **Deal-more-than-you-program** (hand/economy depth).
   - **Objectives-based victory + Heavy/Assault weapon keywords** per the Phase 2.5 design in the finish plan.
   - **Rebalance 160-vs-60 HP and the range dynamics** so the short-range brawler can actually close instead
     of being chunked on approach (fix the speed/range triangle).
   - **Fix pacing** so "watch it play" is a match, not a ~16s burst.

---

## 6. Durable pointers

- `main` @ **`f869d6a6bf9d21d7b627276d9e22f0b50fd5d1df`** (= #109 merge commit), CI 4/4 green.
- Finish plan: `docs/plans/2026-07-21-steel-onslaught-finish-plan.md` (includes Phase 2.5 design).
- Finish audit: `docs/2026-07-21-steel-onslaught-finish-audit.md` + machine-readable
  `docs/2026-07-21-steel-onslaught-finish-audit-findings.json`.
- Live-run screenshots: `docs/evidence/2026-07-21-live-run/{02-configured,03-just-started,04-running}.png`.
- Stall fix PR: <https://github.com/jonahgabriel/steel_onslaught/pull/115> (MERGEABLE, not merged).
- Docs PR (this handoff): <https://github.com/jonahgabriel/steel_onslaught/pull/108> (branch `docs/so-finish-plan`).
