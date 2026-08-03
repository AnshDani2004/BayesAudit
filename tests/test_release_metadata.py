from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import tomli
import yaml

import bayesaudit

ROOT = Path(__file__).resolve().parents[1]


def test_package_version_is_public_release_candidate() -> None:
    pyproject = tomli.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == "1.0.0"
    assert bayesaudit.__version__ == "1.0.0"
    assert pyproject["project"]["authors"] == [{"name": "Ansh Hemang Dani"}]
    assert pyproject["project"]["urls"]["Repository"] == (
        "https://github.com/AnshDani2004/BayesAudit"
    )


def test_citation_and_license_metadata_are_aligned() -> None:
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert citation["version"] == "1.0.0"
    assert citation["repository-code"] == "https://github.com/AnshDani2004/BayesAudit"
    assert citation["authors"][0]["given-names"] == "Ansh Hemang"
    assert citation["authors"][0]["family-names"] == "Dani"
    assert "Ansh Hemang Dani" in license_text
    assert "example/" + "bayesaudit" not in citation["repository-code"]


def test_cli_version_output() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "bayesaudit.cli", "--version"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.strip() == "bayesaudit 1.0.0"


def test_release_facing_files_do_not_contain_stale_metadata() -> None:
    release_files = [
        ROOT / "README.md",
        ROOT / "pyproject.toml",
        ROOT / "CITATION.cff",
        ROOT / "LICENSE",
        ROOT / "docs" / "final_report.md",
        ROOT / "docs" / "portfolio_summary.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in release_files)
    assert "example/" + "bayesaudit" not in combined
    assert "BayesAudit " + "contributors" not in combined
    assert 'version = "0.' + '1.0"' not in combined
