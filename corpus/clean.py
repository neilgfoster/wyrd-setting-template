#!/usr/bin/env python3
"""Strip OCR noise from extracted text. Full-page art OCRs to garbage; drop it.

A line is kept if it looks like language: enough characters, a sane ratio of letters to
junk, and at least one recognisable word. Conservative -- it is better to keep a doubtful
line than to lose a rules table.

Adapted from wyrd-research/corpus/clean.py (that repo is retired; this is the reference
implementation this pipeline ports -- see corpus/README.md). Usage differs slightly: this
version takes a single source file and a single destination file (as corpus/extract.sh calls
it, one PDF at a time) rather than a directory of many files.

Usage:
    corpus/clean.py <src.txt> <dst.txt>
"""

import pathlib
import re
import sys

WORD = re.compile(r"\b[A-Za-z]{3,}\b")


def keep(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if len(s) < 3:
        return False
    alpha = sum(c.isalpha() or c.isspace() for c in s)
    if alpha / len(s) < 0.65:  # mostly punctuation/symbols => art noise
        return False
    words = WORD.findall(s)
    if len(words) < 2:  # single stray words are usually map labels or art noise
        return False
    # a line of single letters and fragments
    if len("".join(words)) / max(len(s), 1) < 0.55:
        return False
    return True


def clean(text: str) -> str:
    out: list[str] = []
    blank = False
    for ln in text.splitlines():
        if keep(ln):
            out.append(ln.rstrip())
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <src.txt> <dst.txt>", file=sys.stderr)
        return 2
    src = pathlib.Path(argv[1])
    dst = pathlib.Path(argv[2])
    raw = src.read_text(errors="replace") if src.exists() else ""
    cleaned = clean(raw)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(cleaned, encoding="utf-8")
    print(f"{len(raw):,} -> {len(cleaned):,} chars ({100 * len(cleaned) / max(len(raw), 1):.0f}% kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
