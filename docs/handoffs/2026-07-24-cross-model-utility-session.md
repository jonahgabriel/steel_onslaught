# Steel Onslaught — Session Handoff (FINAL, 2026-07-23 → 2026-07-24)

Repo `jonahgabriel/steel_onslaught`, default branch `main`, head **`378d7d7`** (= #155). This is the authoritative session-close handoff; it supersedes the interim handoff (PR #150 + #153 refinement) landed earlier in the session. CI = 4 required checks (evidence-schema, frontend-test, python-test, sanitize-text), all green on every merge. Every battery number below was adversarially recomputed from raw event ledgers by an independent agent — not author self-report.

---

## 0. What this project actually IS (north star — read first)

**Steel Onslaught is not primarily an LLM-behavior study. It is a legible, walkable demonstration of the OmniNode architecture** — a deterministic, contract-driven, declarative, event-sourced, replay-auditable, distributed system — in a domain (a mech duel) a person can actually follow. "Deterministic contract-driven declarative distributed architecture" is un-explainable jargon; the game is its concrete referent. The architecture's properties map onto mechanics you can point at:

- **Contracts** → the card/arena/loadout YAML. Nothing runs that isn't declared.
- **Event-sourced truth** → the match ledger. The leaderboard and keep-rate are *projections*, not stored facts.
- **Deterministic replay** → `all_replay_valid=true` on every battery: reconstruct the exact match from the log, get the identical result. This is the headline property, shown live.
- **Declarative config** → overlays. Swap qwen35 → gemma → GLM, symmetric → asymmetric arena, by editing a file — zero code. This session *was* that demo, five times over.

The LLM experiments are a *use* of the substrate — they prove a rigorous, auditable, reproducible experiment program can run end-to-end on it. The behavioral finding is a byproduct of exercising the machine in public.

**Implication for next session:** if legibility is the goal, the highest-value next artifact may be a narrated **architecture tour** (contract → event → replay → declarative-swap → projection, ~30s each, each ending in "…and this is exactly how the platform works"), NOT another model arm. See §5.

**Tension to hold:** legibility and experimental depth pull opposite directions. Every mechanic added for the experiments (heat, over-deal, utility cards, objectives, VP, asymmetric arenas) makes the game a richer test rig and a *worse* minimal teaching example. And the game demonstrates the programming MODEL (contracts/events/replay/declarative config) well, but the distributed RUNTIME (network, partial failure, cross-service projections) much less — it runs mostly in-process.

---

## 1. The finding (final, refined across 4 model families + 2 scenarios)

**LLM tactical planners systematically under-use available counterplay on the AGGRESSIVE archetype, regardless of model family or scenario. The effect's SCOPE (which archetypes, how sharply) is model-dependent.** Utility keep-rate = utility cards programmed into registers ÷ utility cards dealt, per seat; chance floor = 0.50 (all-card keep-rate is exactly 0.5000 for every seat/model — the utility gap is a *selection* effect, not a dealing artifact).

- **GENERAL (architecture-independent, 4/4 lineages):** the aggressive/berserker (red) seat programs utility far below chance in *every* family. This is the load-bearing, robust result — holds across clean and confounded arms alike.
- **LINEAGE-SPECIFIC / a gradient, not a clean split:** whether the defensive/sniper (blue) seat *also* suppresses weakens across models — clear on qwen35 (0.17), softer on gemma (0.32) and deepseek (0.41, mild), and gone on GLM (0.51, at chance). So "both seats suppress" is not general; it's a gradient that breaks by GLM.
- **SCENARIO-ROBUST:** qwen35 suppresses on both the asymmetric-objective and symmetric arenas (magnitude ~35–42% lower on symmetric, same sign).
- **Capability axis (n=4, directional only):** the lowest-power model (glm-4.5) showed the *sharpest* seat split (5.4×), not uniform suppression — capability sharpens the seat split, not the magnitude.

**Honest limits (do not overclaim):** n=4 correlated same-era models, one game, ~n=19–30 each, 3 of 4 non-qwen arms confounded (deepseek abort storm→rerun; gemma cap-truncated; GLM red 63% abort). The *direction* is solid; cross-model *magnitudes* are soft. **Unclosed construct-validity hole:** on the asym arena utility genuinely doesn't help the brawler win (sniper wins ~all) — so sub-chance keep may partly be the model *correctly* declining a low-value tool, not a blind spot. Separating "won't use counterplay" from "correctly declines a weak tool" is the single most important open question — the structural-nudge experiment (§5) begins to probe it.

### Final keep-rate table (red = aggressive/berserker, blue = defensive/sniper)
| Model | Lineage | red keep | blue keep | blue/red | n / caveat |
|---|---|---|---|---|---|
| qwen35 | Alibaba Qwen | 0.0552 | 0.1657 | 3.0× | clean, n=30 (the anchor) |
| deepseek-v4-flash | DeepSeek | 0.1223 | 0.4065 | 3.3× | CLEAN, n=22 (killed for time; supersedes the confounded 0.0735/0.3088) |
| gemma-4-26b | Google Gemma | 0.1776 | 0.3224 | 1.8× | n=19 partial (OpenRouter free-cap) |
| glm-4.5 | Zhipu/GLM | 0.0942 | 0.5130 | 5.4× | n=30, red confounded (63% abort), blue AT chance |
| qwen35 (symmetric arena) | — | 0.0319 | 0.1233 | 3.9× | n=30, scenario-variation |

---

## 2. What was built + merged this session (~19 PRs, each adversarially verified)

Phase-2 utility mechanic + measurement infra:
- #136 Phase 2 utility cards (event/payload/census/fold/LOS+targeting+lock consults/handlers + dealer/Stage-A remediation).
- #137 asym+utility O-GATE overlay + `--overlay` driver arg. #139 **surfacing fix** (stop leaking resolution-priority as strength + describe utility effects — corrected a real prompt bug). #147 `--expected-arena` arg. #148 symmetric utility overlay.

Cross-model wiring (reusable): #141 qwen27 (endpoint non-viable). #142/#144 deepseek. #145 gemma/OpenRouter (secret injection `_EnvBackedSecretResolver` + 429-retry). #151 GLM (`thinking:{type:disabled}` typed field + secret injection) / #152 (retry resilience — timeout retryable, relaxed the selected-provider single-attempt guard).

Evidence docs on `main` (durable, cited): `docs/evidence/2026-07-23-ugate-asym-utility-battery.md`, `-utility-surfacing-fix-remeasure.md`, `-crossmodel-b-deepseek.md`, `-scenario-variation-qwen35-symmetric.md`; `docs/evidence/2026-07-24-crossmodel-b-deepseek-clean.md`, `-crossarch-b-gemma.md`, `-crossarch-glm-lowpower.md`; handoff `docs/handoffs/2026-07-24-cross-model-utility-session.md`.

Two prior-session PRs intentionally left open: **#116** (balance evidence), **#108** (finish-plan docs). Do not touch.

---

## 3. Retained battery baselines (data-bearing worktrees — do NOT prune)

`.onex_state/steel_onslaught/` under each worktree:
- `SO-PROMPT-SURFACING/…/ugate_surfacing_fix_battery` — qwen35 asym surfaced-fixed n=30 (THE anchor).
- `SO-SCENARIO-SYM2/…/ugate_qwen35_symmetric_battery` — qwen35 symmetric n=30.
- `SO-B-DEEPSEEK-RERUN/…/ugate_deepseek_clean_battery` — deepseek CLEAN n=22.
- `SO-B-GEMMA/…/ugate_gemma_battery` — gemma n=19.
- `SO-B-GLM2/…/ugate_glm_battery` — glm-4.5 n=30.
- `SO-B-DEEPSEEK/…/ugate_surfacing_deepseek_battery` — deepseek confounded (superseded; keep for provenance).
- Prior §6 baselines still retained: `SO-UGATE-ASYM`, `SO-L2SIG`, `lgate2`, `so-ogate`, `exp1`, `SO-C11-COOLDOWN`.

Prunable (no unique data): `SO-UTILITY`, `SO-B-QWEN27` (non-viable), `SO-SCENARIO-SYM` (superseded by SYM2), all `SO-EVIDENCE-*` / `SO-HANDOFF*` doc worktrees (merged). Run the git-gc + worktree prune next session.

---

## 4. Housekeeping / open threads

- **LEARNINGS.md is committed-LOCAL, NOT pushed** (all session entries: deepseek/gemma/scenario/glm/deepseek-clean). The omni_home branch `jonah/docs-omni-home-refresh-20260630` was advanced by a **concurrent session** all night (repeated non-fast-forward); pushes were refused and NOT force/rebased (the branch also carries operator WIP — do not stash). **All findings are durable in the steel_onslaught evidence docs on `main`** — no science is at risk. Reconcile the LEARNINGS commits by cherry-picking/rebasing onto the updated remote at a quiet moment.
- **Secrets:** OpenRouter `OPEN_ROUTER_API_KEY` and GLM `LLM_GLM_API_KEY` live in `~/.omnibase/.env` → `secret://llm/{openrouter,glm}`, injected at the battery edge, never committed/printed (verified no key in any diff).
- **Endpoint notes:** qwen35 `:8000` (vLLM, fast). qwen27 `:8001` NON-VIABLE (~4.5 tok/s + reasoning_content empty-content trap). **deepseek: use OpenRouter next time, NOT the local `.200` endpoint** — the local one is impractically slow (~32 min/match at max_tokens 16384; killed the n=30 at 22/30 after ~14h). GLM z.ai coding endpoint works with `thinking:{type:disabled}` (glm-4.5) but the berserker seat emits many invalid plans (63% abort) — a model-quality issue.
- **git-gc (OMN-14760/F-21) ran:** 22 clones gc'd; `onex_change_control` repack FAILED (`fatal: bad object worktrees/-occ-dev-wt-5xoiq7pd/HEAD` + stale `.git/gc.log`) — pre-existing, non-destructive; OCC won't auto-gc until the stale worktree ref + gc.log are cleared.
- **#148 cosmetic:** the symmetric overlay header comment was copied from the asym overlay (describes objectives/vp that don't apply) and its ledger state-paths name the asym lane — harmless (battery used `--state-root`), cleanup later.

---

## 5. Follow-ups for NEXT SESSION (operator decides — do NOT auto-start)

Ordered by my read of value; the operator picks direction next session.

1. **Architecture-legibility artifact (per §0 north star).** A tight, narrated architecture tour through the game — contract → event log → replay reproduction → declarative behavior-swap → truth-as-projection. Likely worth more than any additional science. If legibility is the actual goal, this is the lead candidate.
2. **Structural-nudge experiment (the constructive science).** Does an explicit in-register *incentive/mechanism* (not prompt guidance — the L-GATE-2 work showed guidance doesn't steer qwen35) push keep-rate ABOVE chance? Tests the design thesis ("mechanism, not model, forces surfacing") AND begins to close the construct-validity hole (§1: blindness vs correct-decline-of-a-weak-tool). Free/local on qwen35.
3. **Firm the cross-arch claim:** gemma → n=30 (OpenRouter `:free` daily-reset gated; resume seeds 5020–5030 with completion-level retry, NOT whole-match retry); optional 5th free lineage (Mistral). deepseek via OpenRouter for a fast clean n=30.
4. **Single-axis scenario test** (same geometry, toggle objectives only) to attribute the symmetric-arena magnitude drift.
5. **Original game-design track (still open):** utility did NOT make the brawler viable (sniper wins ~all). Objective-placement / VP-pacing re-cut, or the mechanism from #2, to make the brawler actually competitive — the Steel Onslaught depth program that spawned this whole investigation.
6. **Write-up:** the finding + the method (event-sourced, replay-auditable, adversarially-verified LLM-behavior measurement) as a synthesis/draft.

---

## 6. Session close state (2026-07-24)

Nothing running. Both experimental axes answered across 4 lineages + 2 scenarios; all 5 batteries captured, adversarially recomputed, durable on `main`. deepseek-clean landed (n=22). The interim handoff is superseded by this doc.
