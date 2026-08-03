from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_public_assets_and_tables_exist() -> None:
    assets = [
        "architecture.svg",
        "experimental_program.svg",
        "phase8_attack_effect.png",
        "monitor_comparison.png",
        "phase8_phase9_comparison.png",
        "provider_cost_summary.png",
        "cost_usd_summary.png",
    ]
    for name in assets:
        path = ROOT / "docs" / "assets" / name
        assert path.exists(), name
        assert path.stat().st_size > 1000, name
    assert (ROOT / "docs" / "assets" / "phase8_attack_effect.png").read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )

    final_results = (ROOT / "docs" / "tables" / "final_results.md").read_text(
        encoding="utf-8"
    )
    inventory = (ROOT / "docs" / "tables" / "experiment_inventory.md").read_text(
        encoding="utf-8"
    )
    assert "Phase 8 attacked no-oversight positives | 7 | 24 matched quartets" in final_results
    assert "Phase 9 held-out attacker positives | 4 | 12 matched quartets" in final_results
    assert "Phase 9 held-out robustness | 48 | 144 | 144 | 164693" in inventory


def test_release_material_is_publication_ready() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = (ROOT / "docs" / "RELEASE_NOTES_v1.0.0.md").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "release_checklist.md").read_text(encoding="utf-8")
    assert "Phase 9 did not replicate" in changelog
    assert "BayesAudit v1.0.0 Release Notes" in notes
    assert "Phase 9 held-out nonreplication" in notes
    assert "No final-output violations" not in notes
    assert "0 final-output violations" in notes
    assert "Create a merge commit" in checklist
    stale_candidate = ROOT / "docs" / ("release_candidate_" + "v1.0.0.md")
    assert not stale_candidate.exists()


def test_security_audit_patterns_and_allowlist() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "security_audit", ROOT / "scripts" / "security_audit.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    cases = {
        "populated_openai_key_assignment": "OPENAI_API_KEY" "=" "abc123",
        "sk_style_key": "sk-" + "a" * 24,
        "private_key_block": "-----BEGIN " + "PRIVATE KEY-----",
        "authorization_bearer": "Bearer" + " abc.def",
        "local_user_path": "/Users/" + "ansh/project",
        "placeholder_repo": "https://github.com/example/" + "bayesaudit",
        "stale_release_version": 'version = "' + "0.1.0" + '"',
    }
    for name, text in cases.items():
        assert module.PATTERNS[name].search(text), name
    assert module.ALLOW_EMPTY_ENV.fullmatch("OPENAI_API_KEY" "=")

    result = subprocess.run(
        [sys.executable, "scripts/security_audit.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "security audit passed" in result.stdout


def test_gitleaks_config_is_narrow() -> None:
    data = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert data["extend"]["useDefault"] is True
    allowlists = data["allowlists"]
    regexes = "\n".join(allowlists[0]["regexes"])
    assert "token_hash" in regexes
    assert "match_key_hash" in regexes
    assert "token_ledger_hash" in regexes
    assert not re.search(r"generic-api-key.*false", regexes, flags=re.IGNORECASE)
