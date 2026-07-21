# Steel Onslaught

Steampunk tactical mech battle — event-bus-native, replayable, contract-driven contest framework.

Built on OmniNode primitives: event-sourced workflows, reducer-owned state, effect-node UI projections, deterministic replay.

## Play a match

One command. No flags. A person can clone this repo and watch two visibly
different AI pilots fight on the 60x60 board.

```sh
uv run so play
```

That single command:

- serves the packaged **60x60 split-deck** overlay (`tactical_split_v1_qwen`) —
  a red **berserker** (3 movement / 2 weapon cards) versus a blue **sniper**
  (2 movement / 3 weapon cards);
- exposes **every configured model** (Qwen, GLM, OpenRouter, Gemini, plus a
  human seat) in the two pilot dropdowns, sourced from
  `contracts_data/model_catalogs/configured_v1.yaml`;
- starts the React deck at **http://localhost:5173** and writes the deck's
  bootstrap document for it;
- injects provider credentials from `~/.omnibase/.env`
  (`LLM_GLM_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`) — the browser
  roster still decides which model takes each seat.

Then open **http://localhost:5173**, pick a pilot for each side, and press
**START MATCH**. The match does **not** begin until you press it, and the setup
panel disappears once the match starts (it re-arms when the match ends).

Every launch input has a working default, and every one is overridable:

| Flag | Default |
|---|---|
| `--overlay` | `contracts_data/overlays/tactical_split_v1_qwen.yaml` |
| `--catalog-index` | `contracts_data/model_catalogs/configured_v1.yaml` |
| `--session` | `contracts_data/sessions/local_operator.yaml` |
| `--loadout-red` | `contracts_data/loadouts/llm_qwen35_berserker.yaml` |
| `--loadout-blue` | `contracts_data/loadouts/qwen35/sniper_ironclad.yaml` |
| `--seed` | `7` |
| `--port` | `8765` |
| `--bootstrap-output` | `frontend/.steel-onslaught-bootstrap.generated.json` |
| `--frontend / --no-frontend` | `--frontend` (start the Vite deck too) |

`so play-live` is the same launch without auto-starting the deck — use it when
you already run `npm run dev` yourself, or drive the sockets directly.

> **Credentials:** a seat backed by a secret-bearing provider (for example the
> GLM seats) needs its key in `~/.omnibase/.env`. Keyless local seats (the Qwen
> options served from the AI PC) run without one. If a selected seat has no
> credential the browser reports a per-start command failure — the server keeps
> running so you can pick a different pilot.

## Other commands

```sh
# Headless CLI match — text projection to stdout; the overlay picks the ledger.
uv run so run --overlay contracts_data/overlays/standard_v1_qwen.yaml \
              --loadout-a contracts_data/loadouts/llm_qwen35_berserker.yaml \
              --loadout-b contracts_data/loadouts/llm_qwen27_sniper.yaml \
              --seed 7

# Replay a recorded match to the browser deck (replay-only — it cannot start a
# new match; use `so play` for that).
uv run so serve --overlay contracts_data/overlays/standard_v1_qwen.yaml --match <id>
```

## Current status

The deterministic game/runtime baseline is shipped: the match runner composes
movement, sensors, weapons, armor and damage, heat/boiler failures, mode
transitions, card rounds, scoring, SQLite event ledgers, replay, and the
learning-artifact projection. The React pressure-deck frontend consumes the
canonical WebSocket event stream and includes contract-driven human/model seat
selection.

`so play` is the live, credential-injecting browser launch. The match server
begins a match only when the browser issues its Start Match command, and the
canonical event stream — not the command receipt — is the lifecycle authority
for showing and hiding the launch controls.

Run the deterministic proof locally with:

```sh
PATH="$PWD/frontend/node_modules/.bin:$PATH" uv run pytest -q tests/integration/test_proof_of_life.py
```

The implementation and remaining gates are tracked in `docs/plans/`.
