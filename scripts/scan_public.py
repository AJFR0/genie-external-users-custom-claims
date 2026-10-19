#!/usr/bin/env python3
"""Pre-publish leak scanner.

Flags workspace hosts, tokens, raw ids, internal references and release-stage claims in every
tracked or untracked-but-not-ignored file. Customer names come from a denylist that lives
OUTSIDE the repo (default ~/.config/claims-ref/denylist.txt), because a list of customer
names committed to a public repo would itself be a leak. PDFs are scanned via pdftotext;
images are listed for manual review because words drawn into pixels can't be scanned.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DENYLIST = Path.home() / ".config" / "claims-ref" / "denylist.txt"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SKIP_SUFFIXES = {".ico", ".woff", ".woff2", ".ttf"}

RULES: list[tuple[str, re.Pattern]] = [
    ("workspace host", re.compile(r"[a-z0-9-]+\.(cloud\.databricks\.com|azuredatabricks\.net|gcp\.databricks\.com)", re.I)),  # scan:allow
    ("personal access token", re.compile(r"dapi[0-9a-f]{32}")),  # scan:allow
    ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("long numeric id", re.compile(r"(?<![\d.])\d{15,19}(?![\d.])")),
    ("corporate email", re.compile(r"[A-Za-z0-9._%+-]+@databricks\.com", re.I)),  # scan:allow
    ("internal link", re.compile(r"(?<![\w/.])go/[a-z0-9-]+", re.I)),
    ("ticket id", re.compile(r"\b(ES|XTA|ENGRM|ISS|DB-I)-\d{3,}\b")),  # scan:allow
    ("slack channel", re.compile(r"(?<![(\"'/\w])#[a-z0-9]+(?:-[a-z0-9]+){2,}")),
    ("release-stage claim", re.compile(r"\b(PrPr|PuPr|private preview|not (?:yet )?GA|GA (?:date|by|in)|ETA)\b", re.I)),  # scan:allow
]


def load_denylist(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"denylist not found at {path} (create it; it must stay outside the repo)")
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def _deny_patterns(terms: list[str]) -> list[tuple[str, re.Pattern]]:
    return [(f"denylist: {t}", re.compile(rf"(?<![\w]){re.escape(t)}(?![\w])", re.I)) for t in terms]


def scan_text(text: str, deny_terms: list[str]) -> list[tuple[int, str, str]]:
    patterns = RULES + _deny_patterns(deny_terms)
    findings = []
    for n, line in enumerate(text.splitlines(), 1):
        if "scan:allow" in line:
            continue
        for name, pattern in patterns:
            if pattern.search(line):
                findings.append((n, name, line.strip()[:160]))
    return findings


def list_repo_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root, capture_output=True, text=True, check=True)
    return [root / p for p in out.stdout.splitlines() if p and (root / p).is_file()]


def _pdf_text(path: Path) -> str:
    if shutil.which("pdftotext") is None:
        raise RuntimeError("pdftotext is required to scan PDFs (brew install poppler)")
    return subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=True).stdout


def scan_repo(root: Path, deny_terms: list[str]) -> tuple[list[str], list[Path], int]:
    findings: list[str] = []
    review: list[Path] = []
    scanned = 0
    for path in list_repo_files(root):
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            review.append(path)
            continue
        if suffix in SKIP_SUFFIXES:
            continue
        if suffix == ".pdf":
            text = _pdf_text(path)
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                review.append(path)
                continue
        scanned += 1
        for line, rule, excerpt in scan_text(text, deny_terms):
            findings.append(f"{path.relative_to(root)}:{line}: {rule}: {excerpt}")
    if scanned == 0:
        raise RuntimeError("scanned 0 files: refusing to report a clean result")
    return findings, review, scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--denylist", type=Path, default=DEFAULT_DENYLIST)
    args = parser.parse_args(argv)
    findings, review, scanned = scan_repo(args.root, load_denylist(args.denylist))
    print(f"scanned {scanned} text/PDF files")
    for f in findings:
        print(f"LEAK  {f}")
    for p in review:
        print(f"REVIEW BY EYE  {p.relative_to(args.root)}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
