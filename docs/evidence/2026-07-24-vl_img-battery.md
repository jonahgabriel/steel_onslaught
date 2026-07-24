# ARM V-IMG (Vision-Representation Experiment, Image Arm) Battery — HARD BLOCKED (2026-07-24)

**Verdict:** **VACUOUS / UNTRUSTWORTHY.** 0/30 matches reached a terminal state — only 1 of 30 seeds was even attempted, and that one aborted on the very first LLM call of tick 1. `play_terminal_fraction = 0/1 attempted = 0.0000`, catastrophically below the ≥0.9 trust gate. No win rate, terminal-class mix, keep-rate, cognition-axis, or outcome-axis figure can be computed. This is not a competitiveness result; it is the identical infrastructure failure that already blocked this arm's V-TEXT twin (`docs/evidence/2026-07-24-vl_text-battery.md`), now independently re-confirmed for V-IMG.

**Ledger:** `.onex_state/steel_onslaught/vl_img_battery/` (`events.sqlite3` only — 6 rows, no `battery_raw.jsonl`, no `battery_summary.json`, `leaderboard.sqlite3` present with 0 rows) in the SO-SCREENSHOT worktree.
**Change under test:** PR #171 (merged to `main` at `b47d481de43f6e553776455cb53ea308b69cf49e`) — deterministic arena-screenshot renderer + image-capable `OpenAICompatibleClient`, and this arm's overlay, `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_img.yaml` (V-IMG: adds one `llm.providers[0].image_attachment` block on top of the V-TEXT baseline — a per-tick rendered PNG of the arena attached to the same text prompt). Arena `foundry_60_asym_v2`, loadouts under `contracts_data/loadouts/vision_gemini/` (PR #157 v2 config).
**Model:** `gemini-2.5-flash-lite`, direct (non-OpenRouter) Google API, both seats, target n=30 seeds 5001–5030.
**All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger, a byte-for-byte sha256 spot-check of the persisted PNG, a live re-probe of the same credential/endpoint, and a run of the render-determinism test suite — not copied from the battery runner's report.**

---

## Method

- **Terminal health** = distinct `event_type` values present in `events.sqlite3` for this ledger, checked for `MATCH_ENDED`/`match_ended`/any terminal-completion event.
- **Completion health** = `llm_completion_requested` / `llm_completion_resolved` / `llm_completion_failed` counts and per-event `payload_json` failure codes.
- **Credential/root-cause verification** = independent live `curl` to `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent`, using the same `GEMINI_API_KEY` present in this machine's `~/.omnibase/.env`, run fresh during this verification pass.
- **Vacuity/image check** = (a) grep of `payload_json` across all 6 ledger rows for `image`/`.png`/`sha256` tokens; (b) `find` for every `.png` under the state root's render directory; (c) `shasum -a 256` of the persisted PNG compared byte-for-byte against the ledger's `image_sha256` field; (d) `uv run pytest tests/llm/test_render_determinism.py` to confirm the platform non-negotiable ("same state → byte-identical PNG") holds at the unit level, independent of whether any battery match completed.
- **Additivity check** = `diff` of `vision_foundry_60_asym_v2_gemini_img.yaml` against its V-TEXT twin to confirm the two overlays are identical except the `image_attachment` block and state-root path/name fields; direct read of `scripts/run_ogate_objectives_battery.py` to confirm no exception handling wraps `_run_match`, so a single unhandled provider error aborts the whole battery process.

---

## 1. Completion health (0/30 matches reached terminal; 1/30 seeds even attempted)

| Metric | Value |
|---|---|
| `match_started` events | 1 (seed 5001, `match.01KYAKZXASE1KZ85955VHE7BJW`) |
| `match_tick` events | 1 (tick 1 only — the match never reached tick 2) |
| Any `MATCH_ENDED`/`match_ended`/terminal-completion event | **absent** — confirmed by full enumeration of all 6 ledger rows (`match_started` 1, `match_tick` 1, `boiler_updated` 2, `llm_completion_requested` 1, `llm_completion_failed` 1 — no terminal type in the list) |
| `llm_completion_requested` | 1 |
| `llm_completion_resolved` (succeeded) | **0** |
| `llm_completion_failed` | 1 |
| `battery_raw.jsonl` | does not exist in the state root (confirmed: `_run_match` only appends a row after a match completes, and the runner has no try/except around the call — an unhandled exception on seed 1 aborts the process before any row is written) |
| `battery_summary.json` | does not exist in the state root |
| `leaderboard_entries` rows | 0 |
| **play_terminal_fraction** | **0.0000** (0 decided matches ÷ 1 attempted seed) |
| Seeds never attempted | 5002–5030 (29 of 30 seeds) — the runner correctly stopped at the first unhandled exception rather than looping into 29 more guaranteed 429s |

The single `llm_completion_requested` event carries `provider_id: gemini_vl`, `persona_id: berserker`, `image_sha256`, `image_byte_length: 3745` — confirming the image-attachment code path fired correctly before the provider call failed. The subsequent `llm_completion_failed` event (`causation_id` links it to the same request) carries `reason_code: provider_error`, with `model`/`finish_reason`/`prompt_tokens`/`completion_tokens`/`cost_usd` all `null` — consistent with a rejection at the transport layer (HTTP 429) before any tokens were produced, matching the runner's report of an unhandled `LlmTransportError: LLM provider returned HTTP 429`.

## 2. Root-cause verification (independently re-probed, not trusted from the runner's report)

A fresh `curl` was issued during this verification pass, using the same `GEMINI_API_KEY` sourced from this machine's `~/.omnibase/.env`, against `gemini-2.5-flash-lite:generateContent`:

```json
{
  "error": {
    "code": 429,
    "message": "You exceeded your current quota... Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash-lite",
    "status": "RESOURCE_EXHAUSTED",
    "details": [{
      "@type": "type.googleapis.com/google.rpc.QuotaFailure",
      "violations": [{
        "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
        "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash-lite"},
        "quotaValue": "20"
      }]
    }]
  }
}
```

This is the **identical quota** (`quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`) already documented and independently confirmed in `docs/evidence/2026-07-24-vl_text-battery.md` for the V-TEXT twin. `~/.omnibase/.env` was checked and contains exactly one `GEMINI_API_KEY` entry — there is no alternate or billing-enabled key to fall back to. The runner's characterization of this key as "own-billed" (inherited from PR #171's overlay comments: *"own-billed API key, not the shared OpenRouter `:free` pool that truncated the gemma text lane at n=19/30"*) is **not supported by live evidence** — this is the same factual misstatement the V-TEXT evidence doc already flagged against PR #171's merge report, now reconfirmed against the same credential for this arm.

**Ordering matters here.** The V-TEXT battery ran first in this session and consumed 20/20 of the day's quota (20 successful resolutions recorded in `vl_text_battery`'s ledger, per its evidence doc). V-IMG ran second, against the same shared per-project/per-model quota, and inherited **zero** remaining budget — hence 0 successes here versus V-TEXT's partial 20 successes before its own exhaustion. This is consistent with a single shared daily counter, not an image-specific rejection; nothing about attaching an image caused the additional failure.

## 3. Vacuity / image check — render pipeline itself is NOT vacuous

Unlike the V-TEXT arm (which carries no image data by design), V-IMG's single completed pipeline step *did* produce real image artifacts, and those check out cleanly:

| Check | Result |
|---|---|
| Ledger rows containing an `image`/`.png`/`sha256` token | 2 of 6 (`match_started`'s `prompt_provenance.prompts[].prompt_sha256` fields — unrelated to images — and the one `llm_completion_requested` event's `image_sha256`/`image_byte_length` fields) |
| PNG files under the render output dir | 1 — `.onex_state/steel_onslaught/vision_foundry_60_asym_v2_gemini_img/renders/match.01KYAKZXASE1KZ85955VHE7BJW/tick_0001_mech.red.01.png` |
| Ledger `image_sha256` | `1e5e08c6f81dbf7b05a11a40b0ca3f708f4fa45a0399d82e4f0ca1f1553a0b73` |
| `shasum -a 256` of the persisted PNG (independently recomputed) | `1e5e08c6f81dbf7b05a11a40b0ca3f708f4fa45a0399d82e4f0ca1f1553a0b73` — **byte-for-byte match** |
| `uv run pytest tests/llm/test_render_determinism.py` | **9/9 passed** (fresh run this pass, after installing the `dev` extra for `pytest`) |

This confirms the platform non-negotiable this arm depends on — the rendered image is a pure deterministic function of match state, its sha256 is recorded in the ledger, and the PNG is durably persisted under the state root and joinable to that ledger event — holds for the one tick this run reached, and is separately proven at the unit level by the passing determinism suite. **The render/ledger-linkage machinery is verified working; the battery that would exercise it at scale is what's blocked.** These are two independent claims and should not be conflated: a green render-determinism unit suite does not make the battery's outcome data any less vacuous.

## 4. Cognition axis / outcome axis / within-model comparison / cross-model note

Not computable — 0 decided matches, and only 1 tick's worth of pre-completion state exists at all.

- **Outcome axis** (red win rate, terminal-class mix, survival, blue LOS-blocked-shot fraction): no data. No verdict band on red win rate applies.
- **Cognition axis** (terrain/cover/LOS mentions in red rationales, out-of-range fire attempts): no data — the single `llm_completion_requested` never resolved, so no `pilot_decision_made` event, no rationale text, exists anywhere in this ledger.
- **V-IMG vs. V-TEXT within-model comparison** (the entire point of this experiment): **cannot be computed.** Both arms are independently VACUOUS/UNTRUSTWORTHY on the identical shared-credential daily-quota wall — V-TEXT reached `play_terminal_fraction = 0.0000` over 22 attempted matches (0/22, per its own evidence doc), V-IMG reaches `play_terminal_fraction = 0.0000` over 1 attempted match (0/1). This is exactly the outcome the V-TEXT evidence doc predicted ("very likely to hit the same wall if attempted before the quota resets or a billing-enabled key is substituted") — confirmed here, not merely inferred. Zero data exists on either arm to isolate what pixels buy; the experiment as designed cannot answer its own question until the credential problem is fixed.
- **Cross-model, confounded, directional-only note vs. a qwen35 ASCII-representation arm**: no such evidence doc exists in this repo as of this verification pass. The only qwen35 evidence doc present is `docs/evidence/2026-07-23-scenario-variation-qwen35-symmetric.md` (a scenario-variation battery, unrelated to representation), so there is nothing to compare against, directionally or otherwise.

## 5. Additivity / merge verification

- PR #171 merged to `main` at `b47d481de43f6e553776455cb53ea308b69cf49e` (`gh pr view 171`: state MERGED, mergedAt 2026-07-24T17:34:07Z, title "feat: vision pilot — deterministic arena screenshots + image-capable adapter (V-TEXT/V-IMG arms)").
- `diff` of `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_img.yaml` against `..._gemini_text.yaml` confirms the two are identical except: header comments, state-root path/name fields (`vision_foundry_60_asym_v2_gemini_img` vs. `..._text`), `model_identity_id`/`display_name`, and the one added `image_attachment: {enabled: true, arena_size: 60, render_output_dir: ...}` block. Provider `timeout_seconds: 90.0`, `max_tokens: 2048`, and `retry: {max_attempts: 1, initial_backoff_seconds: 0.0, backoff_multiplier: 1.0}` are byte-identical between the two arms — confirmed directly, not assumed.
- Read of `scripts/run_ogate_objectives_battery.py`: `_run_match` (line 280) wraps only the runner/ledger-read in `try/finally` (line 305) — no `except` clause anywhere in the function — and the driving loop (line 511–522) calls `_run_match` with no surrounding `try/except`. A single unhandled provider exception on seed 1 therefore aborts the entire process before any subsequent seed is attempted and before the first `battery_raw.jsonl` row is written. This is the mechanical reason 29 of 30 seeds were never attempted, not a runner bug or a truncated report.
- No code or state was hand-edited during this verification; the worktree (`SO-SCREENSHOT`, `HEAD` at `b47d481`) was inspected read-only plus one diagnostic `curl` against the live Gemini endpoint and one `pytest` invocation against an existing, unmodified test module.

---

## Verdict

**VACUOUS / UNTRUSTWORTHY.** `play_terminal_fraction = 0.0`, catastrophically below the ≥0.9 trust gate — no verdict band on red win rate applies because zero matches ever reached a terminal state, and only 1 of the planned 30 seeds was even attempted before the process aborted. This is a credential/infrastructure failure, independently re-confirmed live and identical in root cause to the already-documented V-TEXT twin: the `GEMINI_API_KEY` bound to `secret://llm/gemini` is a Google AI Studio **free-tier** key subject to a hard **20 requests/day/project/model** ceiling (`quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`), not the "own-billed" credential PR #171's merge report claims. Because V-TEXT ran first in this session and consumed the day's full 20-request allotment, V-IMG inherited zero remaining budget and failed on its very first call. The render/ledger-linkage machinery itself checks out cleanly (deterministic PNG, correct sha256 in the ledger, matching persisted artifact, 9/9 passing determinism unit tests) — the platform non-negotiables this experiment depends on are proven sound at the component level — but the experiment's actual question (does an image change outcomes, holding the model fixed) cannot be answered by either arm on the current credential. Neither the outcome axis nor the cognition axis produced any data, and the within-model V-TEXT/V-IMG comparison that is the entire point of this experiment cannot be computed.

**What's needed before this arm (or its V-TEXT twin) can produce trustworthy data:** either (a) enable billing on the Google Cloud project backing `GEMINI_API_KEY` so the paid tier's higher per-day ceiling applies, or (b) supply a different, billing-enabled key via `secret://llm/gemini`, and then wait for the daily quota window to reset (or use the freshly-billed key) before re-running both arms back-to-back. This finding reinforces, rather than newly discovers, the correction to PR #171's "own-billed" claim already flagged in the V-TEXT evidence doc — no new ticket is needed for that; a re-run of both arms once the credential is fixed is the only outstanding action.

---

## Citations (all relative paths)

- Ledger: `.onex_state/steel_onslaught/vl_img_battery/events.sqlite3` (6 rows total — `match_started`, `match_tick`, `boiler_updated` ×2, `llm_completion_requested`, `llm_completion_failed`); `leaderboard.sqlite3` (0 rows).
- Rendered artifact: `.onex_state/steel_onslaught/vision_foundry_60_asym_v2_gemini_img/renders/match.01KYAKZXASE1KZ85955VHE7BJW/tick_0001_mech.red.01.png` (sha256 `1e5e08c6f81dbf7b05a11a40b0ca3f708f4fa45a0399d82e4f0ca1f1553a0b73`, independently recomputed and matched byte-for-byte).
- Overlay under test: `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_img.yaml`; V-TEXT twin: `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_text.yaml`.
- Merge commit: `b47d481de43f6e553776455cb53ea308b69cf49e` (PR #171, `main`).
- Render determinism unit suite: `tests/llm/test_render_determinism.py` (9/9 passed, this verification pass).
- Independent live credential probe: direct `curl` to `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent`, using the `GEMINI_API_KEY` from this machine's `~/.omnibase/.env`, executed fresh during this verification pass — HTTP 429, `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`.
- Twin arm's evidence: `docs/evidence/2026-07-24-vl_text-battery.md` (V-TEXT: same credential, 0/22 attempted, same root cause, first to flag the "own-billed" claim as unsupported).
- Prior related arms: `docs/evidence/2026-07-23-crossarch-b-gemma.md` (OpenRouter `:free` daily-cap truncation, n=19/30 — the same class of free-tier failure this credential was meant to avoid).
- No secrets, keys, or absolute paths included. The `GEMINI_API_KEY` value itself is never printed or committed anywhere in this document or the underlying probe output.
