# Phase 6 Report

Phase 6 adds selective and adaptive strategic attackers while preserving Phases 1 through 5.

Implemented:

- `bayesaudit.attack.v1` schemas
- attacker observations with knowledge tiers
- synthetic attack primitive catalog
- ten attacker families including evaluation-only oracle
- attack opportunity, decision, event, state, concealment, and outcome records
- attacker-defender smoke matrices
- restricted empirical-game analysis
- selection-bias and displacement helpers
- offline red-team-loop records
- large-run planning output
- CLI validation and inspection commands

Limitations:

- all runs are synthetic
- no real provider calls
- no real external actions
- no unrestricted evasion prompt generation
- game analysis is restricted empirical analysis, not a true equilibrium claim

Phase 7 should begin with a costed, explicitly approved real-model pilot after preserving the Phase 6 synthetic controls and safety gates.
