# Adaptive Red Teaming

The Phase 6 red-team loop is offline and synthetic:

1. Evaluate current attackers against defenders.
2. Identify weaknesses.
3. Add or select an improved restricted attacker.
4. Re-evaluate on non-confirmatory splits.
5. Stop under resource or iteration limits.

Each iteration records attacker version, defender version, training artifacts, evaluation split, improvement, overfitting indicators, and resource use. The loop must not modify frozen confirmatory manifests.
