# Vision Rerun Attempt (V-TEXT/V-IMG, "non-free-tier key") — CREDENTIAL-TIER GATE FAILED, BATTERY NOT RUN (2026-07-24)

**Verdict: STILL BLOCKED. Battery was NOT attempted.** This was a dispatched rerun of the vacuous 2026-07-24 V-TEXT/V-IMG vision-representation experiment (`docs/evidence/2026-07-24-vl_text-battery.md`, `docs/evidence/2026-07-24-vl_img-battery.md`), on the premise that `GOOGLE_API_KEY` in `~/.omnibase/.env` was a distinct, possibly billing-enabled credential from the `GEMINI_API_KEY` that hit the free-tier wall. **That premise is false.** `GOOGLE_API_KEY` and `GEMINI_API_KEY` are byte-identical values — one secret under two variable names, not two credentials — and that shared secret is confirmed, under burst load, to still be a Google AI Studio free-tier key capped at 20 requests/day/project/model. Per the explicit pre-registered hard gate for this rerun ("if BOTH keys are free-tier, STOP and report — do not run a doomed battery"), no battery was launched. This document is the tier-probe evidence, not a competitiveness result.

**No code or overlay changes were made.** This is a pure credential/environment diagnostic; nothing in `contracts_data/` or `src/` changed as a result.

---

## Method

- **Credential-identity check**: compare `GOOGLE_API_KEY` and `GEMINI_API_KEY` (loaded from `~/.omnibase/.env` via `set -a; source ~/.omnibase/.env; set +a`) by length and by `sha256` of the value — never by printing the value itself.
- **Single-call tier probe**: one minimal `generateContent` call per key (`gemini-2.5-flash-lite`, `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent`, key passed via `x-goog-api-key` header, never in the URL or in any logged command).
- **Burst tier probe**: 26 further sequential minimal calls (same endpoint/model, `maxOutputTokens: 4`) to determine the credential's behavior under load — the gate's own instruction is explicit that "absence of an immediate error is NOT proof of a billed tier," so a single 200 is not treated as evidence; only a sustained burst well beyond the free tier's 20/day ceiling would qualify.
- **Vertex AI / service-account check**: grep of `~/.omnibase/.env` for any `VERTEX_*`, `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_*`, or service-account-style entry that would indicate a true Vertex AI (`aiplatform.googleapis.com`) path distinct from the API-key-based Generative Language API.
- No key value was ever echoed, logged, or written to any file; only variable names, lengths, hashes, and HTTP response bodies (which do not contain the key) are cited below.

---

## 1. Credential identity: `GOOGLE_API_KEY` is `GEMINI_API_KEY`

| Check | `GOOGLE_API_KEY` | `GEMINI_API_KEY` |
|---|---|---|
| Present in `~/.omnibase/.env` | yes (1 entry) | yes (1 entry) |
| Length | 39 chars | 39 chars |
| `sha256` of value | `037e9cee91bbdf903e856419295a38dbe75d88a7d540b15c0b8d074f8ce021f3` | `037e9cee91bbdf903e856419295a38dbe75d88a7d540b15c0b8d074f8ce021f3` |
| Shell string equality (`[ "$GOOGLE_API_KEY" = "$GEMINI_API_KEY" ]`) | **IDENTICAL** | |

`~/.omnibase/.env` was also grepped for every other `google`/`gemini`/`genai`/`palm`/`ai_studio`/`aistudio`-matching variable name: only these two exist. There is no second, differently-valued Google/Gemini credential anywhere in the canonical env file. The operator's framing for this rerun ("`GOOGLE_API_KEY` is DISTINCT from `GEMINI_API_KEY`") does not hold at the credential level — it is the same secret exposed under two names, most likely so both the OpenAI-compatible endpoint path (which the codebase's `_SECRET_REF_ENV_NAMES` maps to `GEMINI_API_KEY`, `scripts/run_ogate_objectives_battery.py:100`) and generic Google-SDK tooling (which conventionally reads `GOOGLE_API_KEY`) can resolve the same key.

## 2. Tier probe: free-tier, confirmed under burst load

Single-call probes (before the burst) both succeeded:

| Call | Key used | HTTP | Notes |
|---|---|---|---|
| 1 | `GOOGLE_API_KEY` | 200 | `responseId 6M9jasnfOLLBz7IP2bTr-AY`, `usageMetadata.serviceTier: "standard"` |
| 2 | `GEMINI_API_KEY` | 200 | `responseId 9c9jarL5EKS3qtsPhaW6wQo` |

Per the gate's own instruction, two isolated successes are not evidence of a billed tier (the prior V-TEXT battery's first ~20 calls also succeeded before failing). A 26-call sequential burst was then run against the same key to force the ceiling to reveal itself:

| Metric | Value |
|---|---|
| Burst calls | 26 |
| HTTP 200 | 2 (calls #4, #14) |
| HTTP 429 | 24 |
| `quotaId` on every 429 | `GenerateRequestsPerDayPerProjectPerModel-FreeTier` |
| `quotaMetric` on every 429 | `generativelanguage.googleapis.com/generate_content_free_tier_requests` |
| `quotaValue` on every 429 | `20` |
| `retryDelay` on 429s | 4–5s (a generic RPC hint; per the twin V-TEXT/V-IMG docs, this is misleading for a **daily** quota and does not mean the cap clears in seconds) |

A follow-up single verification call after the burst also returned HTTP 429 with the identical `GenerateRequestsPerDayPerProjectPerModel-FreeTier` quota body (full JSON captured, reproduced below with no key material):

```json
{
  "error": {
    "code": 429,
    "status": "RESOURCE_EXHAUSTED",
    "message": "...Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash-lite...",
    "details": [
      {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
        {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
         "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
         "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash-lite"},
         "quotaValue": "20"}
      ]},
      {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "4s"}
    ]
  }
}
```

**Session total: 29 calls, 4 successes (2 single-probe + 2 in-burst), 25 failures, every failure citing the identical `...FreeTier` quotaId and a 20/day ceiling.** This is the opposite of "a successful burst well beyond 20 requests/day" — it is a burst that reproduced the free-tier ceiling almost immediately. The two isolated 200s are consistent with a small fractional daily allotment having refreshed since the prior battery session fully exhausted this same key's quota earlier on 2026-07-24 (`docs/evidence/2026-07-24-vl_text-battery.md` recorded exactly 20/20 successes before failing), not with a billed tier. **Finding: this credential — under either variable name — is Google AI Studio free-tier, hard-capped at 20 requests/day/project/model for `gemini-2.5-flash-lite`.**

## 3. Vertex AI path: not available

`~/.omnibase/.env` was checked for `VERTEX_*`, `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_*`, or any service-account-style entry: **none exist.** The only Google/Gemini path configured anywhere in this environment is the API-key-based Generative Language API (`generativelanguage.googleapis.com`), which is what both `GOOGLE_API_KEY` and `GEMINI_API_KEY` authenticate against and what is confirmed free-tier above. A true Vertex AI path (`aiplatform.googleapis.com`, service-account or ADC-based, billed against a GCP project rather than an AI Studio free-tier key) is a genuinely different credential and integration surface from what this codebase's `OpenAICompatibleClient`/`_EnvBackedSecretResolver` wiring currently targets (`scripts/run_ogate_objectives_battery.py`, `src/steel_onslaught/cli/play.py`) — escaping the free tier this way would require both a service-account credential and, likely, provider-adapter work this codebase does not yet have (the existing `gemini_vl` provider binding is `kind: openai_compatible` against the AI-Studio-compatible endpoint, not a Vertex AI client).

## 4. Decision: battery not run

Per the rerun's explicit pre-registered gate ("If BOTH keys are free-tier, STOP and report — do not run a doomed battery, and do not quietly downscale to n=5 and present it as a result"): since `GOOGLE_API_KEY` and `GEMINI_API_KEY` are the same free-tier-capped secret, launching either the V-TEXT or V-IMG battery on this credential would reproduce the identical vacuous outcome already documented twice (`vl_text-battery.md`: 0/22 attempted; `vl_img-battery.md`: 0/1 attempted). No battery was launched. No overlay, no ledger, no `battery_raw.jsonl` exists for this attempt — there is nothing to recompute figures from, by design.

## 5. Correction to PR #171 (reinforced, not new)

PR #171's merge report claims: *"Model chosen: `gemini-2.5-flash-lite` via the existing direct (non-OpenRouter) Gemini wiring pattern — **own-billed API key**, not the shared OpenRouter `:free` pool that truncated the gemma text lane at n=19/30."* Both prior evidence docs (`vl_text-battery.md` §3, `vl_img-battery.md` §2) already flagged this as a factual misstatement based on a single live 429 probe each. This document adds a third, stronger line of evidence: a 26-call burst against the same credential (reached via a second env-var name the operator believed might be a different, billing-enabled key) reproduces the identical `GenerateRequestsPerDayPerProjectPerModel-FreeTier` ceiling 24/26 times, and proves by `sha256` that there was never a second credential to begin with. The "own-billed" claim in PR #171 is confirmed false, not merely unsupported — every credential available in this environment for this model is the same Google AI Studio free-tier key.

---

## Verdict

**STILL BLOCKED.** No battery run, no PR #171 correction ticket needed beyond what's already flagged (the claim is now conclusively disproven, not just doubted). The rerun's own hard gate did its job: it caught a false premise (a "distinct" credential that turned out to be the identical secret under a second name) before a third vacuous arm could be produced and misreported as new data.

**What is actually needed to unblock this experiment:** a genuinely different, billing-enabled credential value — not another environment-variable alias for the same free-tier key — bound to `secret://llm/gemini`, OR a true Vertex AI service-account path (which this codebase does not yet have a provider adapter for). Neither exists in this environment today. Waiting for the free-tier daily quota to reset (Google AI Studio free-tier daily quotas conventionally reset at midnight Pacific Time; not independently verified against this specific project's reset schedule) would only reproduce the original n<30, quota-truncated vacuous result, not a trustworthy n=30 battery — the daily ceiling of 20 requests/day is far below the ~60+ live LLM calls a single 30-seed, two-seat battery requires.

---

## Citations (all relative paths; no secrets, keys, or absolute paths included)

- Prior vacuous arms: `docs/evidence/2026-07-24-vl_text-battery.md` (0/22 attempted, `GEMINI_API_KEY`, first to flag "own-billed" as unsupported), `docs/evidence/2026-07-24-vl_img-battery.md` (0/1 attempted, same credential, same quota, render/ledger machinery independently verified sound).
- Overlays (unmodified by this attempt): `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_text.yaml`, `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_img.yaml`.
- Secret-ref → env-var mapping: `scripts/run_ogate_objectives_battery.py:88-101` (`secret://llm/gemini` → `GEMINI_API_KEY` only; `GOOGLE_API_KEY` is not in this mapping and was probed directly via `curl`, not through the battery driver).
- Merge commit under correction: `b47d481de43f6e553776455cb53ea308b69cf49e` (PR #171, `main`).
- Live credential-identity check: `sha256`/length comparison of `GOOGLE_API_KEY` vs. `GEMINI_API_KEY` loaded from `~/.omnibase/.env`, executed fresh this session — byte-identical.
- Live tier probe: 2 single calls + 26-call burst + 1 verification call (29 total) against `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent`, executed fresh this session — 4×200, 25×429 (`quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`).
- Vertex AI availability check: grep of `~/.omnibase/.env` for `VERTEX_*`/`GOOGLE_APPLICATION_CREDENTIALS`/`GCP_*`/service-account entries — none found.
