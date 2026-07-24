# Steel Onslaught — Session Handoff (2026-07-23 → 2026-07-24)

Repo `jonahgabriel/steel_onslaught`, default branch `main`. All PR/CI/SHA facts read live via `gh`/`git`.
`main` head after this session: **`ea6ca7b`** (= #149 merge). CI = 4 required checks (evidence-schema, frontend-test, python-test, sanitize-text); all green on every merge below. Playwright proof-of-life is deselected local-only (green in CI).

---

## 1. Headline finding (durable, cited across 7 evidence docs on `main`)

**An LLM tactical planner will not surface tactically-available counterplay to its chance floor on its own. This reluctance is GENERAL across model families and ROBUST across scenarios.** The design must FORCE utility surfacing via mechanism (reward shaping / scaffold / explicit incentive) — not trust emergent model behavior.

Two axes, both measured with adversarial recompute from raw sqlite ledgers (never author self-report):

### Architecture axis → GENERAL
Utility keep-rate = utility cards programmed into registers ÷ utility cards dealt, per seat. Chance floor = 0.50 (all-card keep is exactly 0.5000 for every seat/model, proving the utility gap is a *selection* effect, not a dealing artifact).

| Model | Lineage | red keep | blue keep | n |
|---|---|---|---|---|
| qwen35 (surfacing-fixed) | Qwen / open-weight CoT | 0.0552 | 0.1657 | 30 |
| deepseek-v4-flash (confounded) | DeepSeek / open-weight CoT | 0.0735 | 0.3088 | 30 (all aborted — directional) |
| Gemma-4-26b (free, OpenRouter) | Google / instruct, non-reasoning — INDEPENDENT | 0.1776 | 0.3224 | 19 (partial) |

All three program utility far below the 0.50 floor on both seats, same blue>red ordering. Gemma — a genuinely different lineage — is the strongest datapoint (breaks the "open-weight-CoT tradition artifact" alternative). Even the most utility-friendly model measured (Gemma) is still decisively sub-chance.

### Scenario axis → ROBUST
| Scenario (qwen35) | red keep | blue keep |
|---|---|---|
| Asymmetric objective arena (foundry_60_asym_v1) | 0.0552 | 0.1657 |
| Symmetric arena (foundry_60, no objectives) | 0.0319 | 0.1233 |

Same sign, same blue>red ordering; magnitude ~35–42% lower on symmetric (MIXED on degree, robust on sign). The red-under-blue asymmetry tracks the *losing seat + model*, not the arena — which is why it survives the arena swap.

### Earlier this session (the road to the above)
- **O-GATE re-measure (utility cards, pre-surfacing-fix):** U-GATE FAILED — qwen35 dumped utility at ~2–6% keep-rate; brawler still 0/30 VP, sniper 30/30. (docs/evidence/2026-07-23-ugate-asym-utility-battery.md)
- **Confound-check (C):** the ~2–6% was PARTLY our own bug — the programming prompt leaked an internal resolution-priority integer (utility lowest) under a "keep the strongest card" instruction, and never described what utility cards do. Fixed in #139 (removed the priority leak, added tactical effect descriptions).
- **Surfacing-fix re-measure:** keep-rate rose ~3× (red 0.0172→0.0552, blue 0.0567→0.1657) but stayed 3–9× sub-chance → deprioritization is GENUINE, not a prompt artifact. This is the qwen35 baseline used above. (docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md)

---

## 2. PRs merged this session (14, each adversarially verified before merge)

| PR | What |
|----|------|
| #136 | Phase 2 utility cards (smoke/chaff/flares: event/payload/census/fold/LOS+targeting+lock consults/handlers/overlay/frontend census/regression) + dealer/Stage-A remediation so utility actually deals+deploys in a live match |
| #137 | Combined asym+utility O-GATE overlay + `--overlay` driver arg + secret_resolver fix |
| #138 | Evidence: U-GATE FAIL / O-GATE unchanged |
| #139 | **Surfacing fix** — stop leaking resolution-priority as strength + describe utility card effects |
| #140 | Evidence: surfacing-fix re-measure (deprioritization survives) |
| #141 | qwen27 overlay + `--red/--blue-loadout` args (qwen27 endpoint later found non-viable) |
| #142 | deepseek-v4-flash wiring (overlay + loadouts + pilots) |
| #143 | Evidence: deepseek cross-model B (GENERAL, confounded) |
| #144 | deepseek max_tokens 4096→16384 + timeout (for the clean rerun) |
| #145 | Gemma/OpenRouter wiring (overlay + loadouts + pilots + secret injection + 429-retry) |
| #146 | Evidence: Gemma cross-architecture (GENERAL, n=19 partial) |
| #147 | `--expected-arena` battery driver arg (unblocks non-asym arenas) |
| #148 | Tolerant symmetric utility overlay (foundry_60) |
| #149 | Evidence: scenario-axis SCENARIO-ROBUST |

Two open PRs from prior sessions intentionally left open: **#116** (measured balance evidence, hold), **#108** (finish-plan docs). Do not touch.

---

## 3. Retained battery baselines (data-bearing worktrees — do NOT prune)

State-roots live under each worktree's gitignored `.onex_state/steel_onslaught/`:
- `SO-PROMPT-SURFACING/.../ugate_surfacing_fix_battery` — **qwen35 asym surfaced-fixed, n=30 — THE anchor baseline**
- `SO-UGATE-ASYM/.../ugate_asym_utility_battery` — qwen35 asym pre-surfacing-fix O-GATE, n=30
- `SO-B-DEEPSEEK/.../ugate_surfacing_deepseek_battery` — deepseek confounded, n=30 (all aborted)
- `SO-B-DEEPSEEK-RERUN/.../ugate_deepseek_clean_battery` — **deepseek CLEAN — IN PROGRESS (~10/30 at 00:02, ~26 min/match, ETA ~morning)**
- `SO-B-GEMMA/.../ugate_gemma_battery` — Gemma n=19 partial (free-cap truncated)
- `SO-SCENARIO-SYM2/.../ugate_qwen35_symmetric_battery` — qwen35 symmetric, n=30
- Prior-session §6 baselines still retained: `SO-L2SIG`, `lgate2`, `so-ogate`, `exp1`, `SO-C11-COOLDOWN`.
- Prunable this session (no unique data): `SO-B-QWEN27` (non-viable endpoint), `SO-SCENARIO-SYM` (first attempt, superseded by SO-SCENARIO-SYM2), the `SO-EVIDENCE-*` doc worktrees (merged).

---

## 4. Follow-ups — gated / queued (priority order)

1. **deepseek-clean finishing (~morning).** Task still running. When it lands: capture (evidence doc marking it CLEAN, replacing the confounded #143 number in the synthesis) + append LEARNINGS. Resume/inspect its ledger at `SO-B-DEEPSEEK-RERUN/.../ugate_deepseek_clean_battery`.
2. **Gemma → n=30 (BLOCKED on OpenRouter :free daily reset ~00:00 UTC).** Resume seeds 5020–5030 and merge into the banked n=19. Do NOT use whole-match retry (it amplified request volume and helped exhaust the cap) — first make `invalid_response` retryable at completion-level inside the client's existing 4-attempt backoff (a small, scoped client change), then resume. Overlay: `tactical_split_overdeal_utility_asym_v1_gemma.yaml`; model pinned `google/gemma-4-26b-a4b-it:free`.
3. **More free lineages (also OpenRouter-cap-gated).** After reset, a Mistral / other independent free instruct model strengthens the architecture axis. Free reasoning models (Nemotron, gpt-oss) are unusable (empty/truncate); pick instruct.
4. **Single-axis scenario test.** The current scenario contrast changes geometry AND objectives together. A clean test = same arena geometry, toggle objectives only, to attribute the ~35–42% magnitude drift.
5. **The design-implication experiment (highest scientific value).** All of the above confirm the *negative*; the natural next question is whether a STRUCTURAL nudge (an explicit utility-in-register reward/incentive, not mere prompt guidance — which the L-GATE-2 work already showed doesn't steer qwen35) actually raises keep-rate above chance. This is the "can we fix it" experiment the finding motivates.
6. **Cosmetic cleanup:** #148's symmetric overlay header comment was copied verbatim from the asym overlay (describes objectives/vp that don't apply) and its ledger state-paths still name the asym lane — give it its own paths + correct header.

---

## 5. Housekeeping / open threads

- **LEARNINGS.md is committed-LOCAL, not pushed** (multiple commits: deepseek, gemma, scenario). The omni_home branch `jonah/docs-omni-home-refresh-20260630` has been advanced by a **concurrent session** all evening (repeated non-fast-forward), so pushes were refused and NOT force/rebased. **All findings are durable in the steel_onslaught evidence docs on `main`** — no science is at risk. Reconcile the LEARNINGS commits by rebasing onto the updated remote at a quiet moment (do not force under a live concurrent session; the branch also carries the operator's uncommitted WIP, so do not stash — a manual, careful rebase or cherry-pick is needed).
- **OpenRouter key** lives in `~/.omnibase/.env` as `OPEN_ROUTER_API_KEY` → `secret://llm/openrouter`. Account has ~$44 credit but `:free` models are $0; the ~1000 free-req/day cap is what throttled Gemma. Key was never committed or printed (verified: no `sk-or` in any diff).
- **Endpoints:** qwen35 `omninode-pc.tail75df5e.ts.net:8000` (vLLM, fast); qwen27 `:8001` (llama.cpp, ~4.5 tok/s + reasoning_content empty-content trap — NON-VIABLE for batteries even with `enable_thinking:false` due to throughput); deepseek-v4-flash `stickybeatz-studio.tail75df5e.ts.net:8101` (.200, ~18.5 tok/s).
- No prod anywhere (personal repo). Free/local only was honored — zero spend.

---

## 6. Session close state (as of 2026-07-24 ~00:05)

- Running: **deepseek-clean rerun** (background workflow, ~10/30, healthy, ~morning ETA).
- Gated: Gemma→n=30 + more free lineages (OpenRouter daily reset ~18h).
- Everything else captured, verified, and durable on `main`. Both experimental axes answered.

---

## REFINEMENT (2026-07-24, GLM 4th arm — n=4 models)

The "GENERAL across architectures" headline is REFINED by adding Zhipu/GLM (glm-4.5, lower-power):

- **GENERAL (4/4 lineages):** the AGGRESSIVE/berserker (red) seat programs utility far below chance in every family — qwen35 0.0552, deepseek 0.0735, gemma 0.1776, glm-4.5 0.0942 (all vs 0.50 floor). Aggressive-seat utility suppression is architecture-independent. This is the load-bearing, robust finding.
- **LINEAGE-SPECIFIC:** whether the DEFENSIVE/sniper (blue) seat ALSO suppresses holds for qwen35/deepseek/gemma (blue 0.17–0.32, sub-chance) but BREAKS on GLM — glm-4.5 blue keeps utility AT chance (0.513). The scope (one seat vs both) is not general.
- **Capability axis (n=4, directional only):** the lowest-power model (glm-4.5) shows the SHARPEST seat split (5.4×), not uniform suppression — inconsistent with "lower-power deprioritizes more"; consistent with the seat/role prompt dominating, executed more coarsely by the weaker model.
- **Confound:** GLM red had a 63% abort rate (glm-4.5 emits invalid plans on the berserker seat — model quality, not infra; the retry fix solved only the z.ai timeout stalls, 1/111). Red is a biased survivor sample. The general red-suppression claim survives across clean + confounded arms; the capability reading is directional.

Evidence: docs/evidence/2026-07-24-crossarch-glm-lowpower.md. Wiring: PR #151 (glm-4.5 + thinking:disabled typed field + secret injection), #152 (retry resilience). deepseek-clean rerun still pending (will firm the same-family point).
