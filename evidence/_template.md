---
id: SO-NNNN
title: "one-line title"
status: OPEN            # OPEN | PASS | FAILED
intent: "one line — what this ticket claims to prove"
acceptance_bar:        # PRE-REGISTERED before work starts
  - "concrete, checkable bar #1"
  - "concrete, checkable bar #2"
evidence:
  commits: []          # SHAs
  suite:               # re-checkable command outputs
    pytest: ""         # e.g. "N passed, M skipped"
    mypy_strict: ""    # "clean" | "dirty"
    frontend: ""       # e.g. "N passed"
  ledger: {}           # sqlite counts, match ids, tallies
  checks: []           # ≥1 required once closed: "command → observed result"
  artifacts: []        # file/screenshot paths — each must resolve on disk
verifier: null         # required once closed; identity distinct from the builder
verified_at: null      # required once closed; ISO-8601
---

## SO-NNNN — <title>

Prose narrative: what was done, why, and how the acceptance bar was met.
Keep the *facts* in the frontmatter (CI re-checks those); keep the *story* here.
