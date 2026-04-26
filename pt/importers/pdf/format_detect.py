"""Detect which broker PDF parser to use, based on the first-page text.

Add a new format by:
  1. writing `pt/importers/pdf/<broker>.py` with `can_parse(text) -> bool` and
     `parse(path) -> ParsedStatement`,
  2. importing it here and adding a tuple to `_REGISTRY`.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from pt.importers.pdf import lgt

_REGISTRY = [
    ("lgt", lgt),
    # Future: ("trade_republic", trade_republic),
    # Future: ("scalable", scalable_capital),
    # Future: ("comdirect", comdirect),
]


class UnsupportedFormatError(RuntimeError):
    """Raised when no parser can handle the first-page text."""


def detect(pdf_path: str | Path) -> str:
    """Return the parser name (e.g. 'lgt:vermoegensaufstellung').

    Raises UnsupportedFormatError if nothing matches.
    """
    pdf_path = Path(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0].extract_text() or ""
    for _key, mod in _REGISTRY:
        if mod.can_parse(first_page):
            return mod.PARSER_NAME
    raise UnsupportedFormatError(
        f"No PDF parser matches {pdf_path.name}. First-page snippet: "
        f"{first_page[:200]!r}"
    )


def parser_for(pdf_path: str | Path):
    """Return the parser module that should handle this file."""
    pdf_path = Path(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0].extract_text() or ""
    for _key, mod in _REGISTRY:
        if mod.can_parse(first_page):
            return mod
    raise UnsupportedFormatError(
        f"No PDF parser matches {pdf_path.name}. First-page snippet: "
        f"{first_page[:200]!r}"
    )
