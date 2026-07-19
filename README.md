# Steel Onslaught

Steampunk tactical mech battle — event-bus-native, replayable, contract-driven contest framework.

Built on OmniNode primitives: event-sourced workflows, reducer-owned state, effect-node UI projections, deterministic replay.

## Current status

The deterministic game/runtime baseline is shipped. The match runner composes
movement, sensors, weapons, armor and damage, heat/boiler failures, mode
transitions, card rounds, scoring, SQLite event ledgers, replay, and the
learning-artifact projection. The React pressure-deck frontend consumes the
canonical WebSocket event stream and includes contract-driven human/model seat
selection.

The verified proof-of-life path covers a decisive match and a draw, live state
folding, SQLite persistence, replay equality, CLI projection, and the browser
projection. The injected LLM path is covered by hermetic provider loopback
tests. A manually started browser match against an external provider is still
an explicit product gate; the packaged/default path remains stub-safe and does
not claim an external API is configured.

Run the deterministic proof locally with:

```sh
PATH="$PWD/frontend/node_modules/.bin:$PATH" uv run pytest -q tests/integration/test_proof_of_life.py
```

The implementation and remaining gates are tracked in `docs/plans/`.
