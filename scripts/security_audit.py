"""Fail-fast public-release security checks for tracked files."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "populated_openai_key_assignment": re.compile(
        r"^[ \t]*OPENAI_API_KEY[ \t]*=[ \t]*['\"]?[^#\s]+", re.MULTILINE
    ),
    "sk_style_key": re.compile(r"(?<![A-Za-z0-9_])" + "sk-" + r"[A-Za-z0-9_-]{10,}"),
    "private_key_block": re.compile("-----BEGIN " + r"[A-Z ]*PRIVATE KEY-----"),
    "authorization_bearer": re.compile("Bearer" + r"\s+[A-Za-z0-9._-]+"),
    "local_user_path": re.compile("/Users/" + "ansh/"),
    "placeholder_repo": re.compile("example/" + "bayesaudit"),
    "stale_release_version": re.compile(r"version\s*=\s*['\"]0\.1\.0['\"]"),
}
ALLOW_EMPTY_ENV = re.compile(r"OPENAI_API_KEY\s*=\s*(?:$|#)")


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def main() -> None:
    failures: list[str] = []
    for path in _tracked_files():
        if not path.exists():
            continue
        if path.suffix in {".png", ".parquet"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                if name == "populated_openai_key_assignment" and ALLOW_EMPTY_ENV.fullmatch(
                    match.group(0)
                ):
                    continue
                failures.append(f"{name}: {path.relative_to(ROOT)}")
                break
    if failures:
        raise SystemExit("\\n".join(failures))
    print("security audit passed")


if __name__ == "__main__":
    main()
