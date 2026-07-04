# Evidence tickets (in-repo, OCC-lite)

Same-repo receipts for Steel Onslaught. Full rationale:
`docs/plans/2026-07-03-evidence-tickets-design.md`.

Every non-trivial work item gets one durable, schema-checked file here instead
of burying its proof in a commit message that `git log` eventually swallows.
This keeps the org's receipts discipline (receipts are honesty, not overhead)
while dropping OCC's cross-repo machinery, which buys nothing on a solo,
single-repo project.

## File scheme

`evidence/SO-NNNN.md` — monotonic id, never reused. YAML frontmatter (the
machine-checkable evidence block) + a markdown body (the prose narrative).

## Frontmatter schema (enforced by `scripts/check_evidence_schema.py`)

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | `SO-NNNN`; must equal the filename stem |
| `title` | yes | one line |
| `status` | yes | `OPEN` \| `PASS` \| `FAILED` (terminal states are locked) |
| `intent` | yes | one line — what this ticket claims to prove |
| `acceptance_bar` | yes | list, **pre-registered before work starts** — a bar written after the result is not a bar |
| `evidence.commits` | no | commit SHAs |
| `evidence.suite` | no | map: `pytest`, `mypy_strict`, `frontend`, … (re-checkable) |
| `evidence.ledger` | no | map: sqlite event/match/tally counts |
| `evidence.checks` | for closed | ≥1 mechanically re-runnable check (command → observed result) |
| `evidence.artifacts` | no | file/screenshot paths — each MUST resolve on disk |
| `verifier` | for closed | identity distinct from the builder (§3a) |
| `verified_at` | for closed | ISO-8601 timestamp |

## Two guardrails (what replaces OCC's independence guarantee)

1. **Schema gate** — `scripts/check_evidence_schema.py`, run by the
   `evidence-schema` CI job and by `tests/test_evidence_tickets.py`. A closed
   ticket with no verifier / no re-checkable check is rejected.
2. **Tamper lock** — `tests/test_evidence_tickets.py` asserts every CLOSED
   (`PASS`/`FAILED`) ticket that already existed at the merge-base has ZERO diff
   vs the merge-base blob. A closed ticket is immutable; to revise it, file a new
   `SO-NNNN` that supersedes it — never a silent amend. (A closed ticket that is
   newly introduced in its own PR is exempt until it merges; after that it is
   frozen.)

## Verifier discipline

The `verifier` field is only trustworthy because of the *workflow*: a gate agent
distinct from the builder re-computes the claims before writing `PASS`. On this
solo repo the verifier is still an agent in the same session lineage — fine for a
personal project, explicitly NOT a substitute for CODEOWNERS-approved production
grants (see the design doc §6).
