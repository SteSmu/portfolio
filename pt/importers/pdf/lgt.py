"""Parser for LGT Bank 'Vermögensaufstellung' (asset-snapshot) PDFs.

Format markers (page 1):
  - 'LGT Bank'
  - 'Vermögensaufstellung' (OCR may split with stray spaces — handled)

The PDFs are typically scanned, so OCR makes things noisy:
  - ISIN 'CH0012005267' may render as 'cH001 2005267' (lowercase, embedded space)
  - Or fuse into one token 'cH1243598427' (depends on ligature heuristics)
  - Decimals like '29\\'451.03' may misread as '29\\'451.A3'
  - '%' is sometimes 'o/o' / '0Ä' / 'Yo' / 'Vo'
  - Quantity + EUR market value can be pushed to the row ABOVE the
    currency anchor row (Sandoz, Roche, Alphabet, ...)
  - Or split a price like '201.9400' into '20' and 'r.9400' (Alphabet)

The parser is therefore deliberately permissive: it uses x-coordinate
columns to disambiguate (qty lives at x<150, prices at x∈[700,850], market
value at x>900), records anything weird in `ParsedStatement.warnings`, and
never crashes on a single bad block.

Empirical column layout (LGT 2025):
  ~60-100   Whg.        currency
  ~110-150  Stückzahl   quantity
  ~135-260  Bezeichnung name + country (multi-line)
  ~280-410  ISIN/Valor  ISIN + Bloomberg + GICS (multi-line)
  ~720-770  Einstands-  entry price + entry FX + entry date
  ~800-870  Aktueller   current price + current FX + current date
  ~920-980  Kurswert    EUR market value
  ~1030+    G/V columns + percentages
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

import pdfplumber

from pt.importers.pdf.types import (
    ParsedCashPosition,
    ParsedHolding,
    ParsedStatement,
)

PARSER_NAME = "lgt:vermoegensaufstellung"

SUPPORTED_CURRENCIES = {"CHF", "EUR", "USD", "GBP", "JPY", "AUD", "CAD", "SEK", "NOK", "DKK"}

# Column boundaries on a typical LGT statement (x-pixel units of pdfplumber).
# Measured from the actual reference PDF (1331_001.pdf):
COL_QTY_MAX_X = 145
COL_NAME_MIN_X = 135
COL_NAME_MAX_X = 270
COL_PRICE_MIN_X = 460       # Einstandskurs starts here
COL_PRICE_MAX_X = 570       # Aktueller Kurs ends here
COL_MARKET_MIN_X = 580
COL_MARKET_MAX_X = 650
# Anything beyond ~650 is percentages we want to ignore.

# Tolerant date regex — OCR sometimes substitutes the dot with a hyphen
# (`11.06-2019`) or even a stray glyph between groups.
_DATE_RE = re.compile(r"(\d{2})[.\-/]+(\d{2})[.\-/]+(\d{4})")
_INT_RE = re.compile(r"^\d{1,5}$")
_NUM_TOKEN_RE = re.compile(r"^-?\d{1,3}(?:['\s]?\d{3})*(?:\.\d+)?$")
_PERCENT_HINT = ("%", "o/o", "0Ä", "Yo", "Vo")

# Bloomberg-style 2-letter exchange suffixes seen on LGT statements.
# Note: LGT uses 'SE' for SIX Swiss Exchange (Sandoz, Novartis, Roche), not the
# vanilla-Bloomberg meaning of 'Stockholm'. We just need to recognise the suffix
# to pair it with a preceding ticker — downstream code uses only the bare ticker.
_BLOOMBERG_EXCHANGE_CODES = frozenset({
    # United States
    "UW", "UN", "UQ", "UF", "UA", "UP", "UR", "US", "UV",
    # Europe
    "FP",                # Euronext Paris
    "GR", "GY",          # Xetra / Frankfurt
    "SE", "SW", "VX",    # SIX Swiss / Stockholm
    "LN",                # London
    "NA",                # Euronext Amsterdam
    "BB",                # Madrid / Berlin
    "IM",                # Borsa Italiana
    "AV",                # Wiener Borse
    "SS",                # OMX Stockholm
    # Asia-Pacific
    "JT", "JP",          # Tokyo
    "HK",                # Hong Kong
    "AU",                # ASX
    "SP",                # Singapore
    "KS",                # Korea
})

# x-bounds of the ISIN/Bloomberg/GICS column on LGT statements.
COL_BLBG_MIN_X = 270
COL_BLBG_MAX_X = 450


# ---------- public API ---------------------------------------------------------

def can_parse(first_page_text: str) -> bool:
    no_ws = re.sub(r"\s+", "", first_page_text)
    return "LGTBank" in no_ws and "Vermögensaufstellung" in no_ws


def parse(pdf_path: str | Path) -> ParsedStatement:
    pdf_path = Path(pdf_path)
    raw = pdf_path.read_bytes()
    file_hash = hashlib.sha256(raw).hexdigest()
    warnings: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        if not can_parse(first):
            raise ValueError(f"Not an LGT Vermögensaufstellung: {pdf_path}")

        all_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        customer = _extract_customer(all_text)
        stmt_date = _extract_statement_date(first)
        base_ccy = _extract_base_currency(all_text)

        holdings: list[ParsedHolding] = []
        cash: list[ParsedCashPosition] = []
        for page in pdf.pages:
            holdings.extend(_parse_aktien_page(page, warnings))
            cash.extend(_parse_konten_page(page, warnings))

    holdings = _dedup_holdings(holdings)

    return ParsedStatement(
        parser=PARSER_NAME,
        customer=customer,
        statement_date=stmt_date,
        base_currency=base_ccy,
        file_hash=file_hash,
        file_name=pdf_path.name,
        holdings=holdings,
        cash=cash,
        warnings=warnings,
    )


# ---------- header parsing -----------------------------------------------------

def _extract_customer(text: str) -> str:
    m = re.search(r"Kunde[:\s]*\n\s*([A-Za-zÄÖÜäöüß][\w \-äöüÄÖÜß]+)", text)
    if not m:
        m = re.search(r"Kunde:\s*([A-Za-zÄÖÜäöüß][\w \-äöüÄÖÜß]+)", text)
    return m.group(1).strip() if m else "?"


def _extract_statement_date(text: str) -> date:
    # OCR may break 'Vermögensaufstellung' but 'per dd.mm.yyyy' stays intact
    m = re.search(r"per\s+(\d{2})\.(\d{2})\.(\d{4})", text)
    if not m:
        raise ValueError("LGT statement date not found in header")
    d, mo, y = m.groups()
    return date(int(y), int(mo), int(d))


def _extract_base_currency(text: str) -> str:
    m = re.search(r"Referenzwährung\s*[:\n]\s*([A-Z]{3})", text)
    return m.group(1) if m else "EUR"


# ---------- row clustering -----------------------------------------------------

def _cluster_rows(words, *, y_tolerance: float = 3.0) -> list[list]:
    rows: list[list] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for r in rows:
            if abs(r[0]["top"] - w["top"]) < y_tolerance:
                r.append(w)
                break
        else:
            rows.append([w])
    for r in rows:
        r.sort(key=lambda w: w["x0"])
    rows.sort(key=lambda r: r[0]["top"])
    return rows


def _row_text(row) -> str:
    return " ".join(w["text"] for w in row)


# ---------- aktien (holdings) section ------------------------------------------

def _parse_aktien_page(page, warnings: list[str]) -> list[ParsedHolding]:
    words = page.extract_words(use_text_flow=False, x_tolerance=2, y_tolerance=2)
    if not words:
        return []
    rows = _cluster_rows(words)

    aktien_start = None
    for i, r in enumerate(rows):
        text = _row_text(r)
        # OCR sometimes mangles 'S' → '5' or '$', and 'I' → 'l' / '|'.
        # Match permissively.
        normalized = re.sub(r"[5$]tückzahl|S?tückzahl", "Stückzahl", text)
        if "Stückzahl" in normalized and (
            "Bezeichnung" in text or "Valor" in text or "ISIN" in text
            or "lSlN" in text or "ISlN" in text
        ):
            aktien_start = i
            break
    if aktien_start is None:
        return []

    holdings: list[ParsedHolding] = []
    i = aktien_start + 1
    while i < len(rows):
        anchor = rows[i]
        first_text = anchor[0]["text"] if anchor else ""
        # Stop at the table footer
        if first_text in {"Total", "Verwendete", "Währung", "Summe"}:
            break
        if anchor and first_text in SUPPORTED_CURRENCIES:
            try:
                holding = _parse_holding_block(rows, i, warnings)
                if holding:
                    holdings.append(holding)
            except Exception as e:
                warnings.append(f"holding parse failed at row y={anchor[0]['top']:.0f}: {e}")
        i += 1
    return holdings


def _parse_holding_block(rows, anchor_idx: int, warnings: list[str]) -> ParsedHolding | None:
    """Build the logical block for one holding and extract its fields."""
    anchor_row = rows[anchor_idx]
    currency = anchor_row[0]["text"]
    anchor_y = anchor_row[0]["top"]

    # Logical block = up to two rows above (visually adjacent) + anchor + rows below.
    # The Airbus pattern needs two-above (qty at y=274, wrap at y=278, anchor at y=279).
    # The Sandoz pattern only needs one-above. Cap at 10px total above the anchor
    # so we don't accidentally absorb the Aktien table header.
    block_words: list = []
    for k in (2, 1):
        idx = anchor_idx - k
        if idx >= 0:
            prev = rows[idx]
            if prev and prev[0]["top"] > anchor_y - 10:
                block_words.extend(prev)
    block_words.extend(anchor_row)

    y_max = anchor_y + 70
    j = anchor_idx + 1
    while j < len(rows) and rows[j][0]["top"] < y_max:
        cur_row = rows[j]
        first = cur_row[0]["text"] if cur_row else ""
        # Stop if the next anchor (CCY at start of a row) is reached
        if first in SUPPORTED_CURRENCIES:
            break
        # Stop at the table footer
        if first in {"Total", "Verwendete", "Währung", "Summe"}:
            break
        # Look ahead: the row immediately preceding a CCY anchor (or the
        # footer) is the "orphan above" of that next entity — don't absorb it.
        if j + 1 < len(rows) and rows[j + 1]:
            nxt = rows[j + 1][0]["text"]
            if nxt in SUPPORTED_CURRENCIES or nxt in {"Total", "Verwendete"}:
                break
        block_words.extend(cur_row)
        j += 1

    block_words.sort(key=lambda w: (w["top"], w["x0"]))
    block_text = " ".join(w["text"] for w in block_words)

    qty = _find_qty(block_words, currency)
    if qty is None:
        warnings.append(f"missing qty: {block_text[:120]}")
        return None

    isin = _extract_isin_from_tokens(block_words)
    entry_date, current_date = _extract_dates(block_words)
    entry_price, current_price = _extract_prices(block_words, qty)
    market_value = _extract_market_value(block_words, qty, entry_price, current_price)
    name = _extract_name(block_words, qty, currency, isin)
    asset_type = _guess_asset_type(block_text)
    bloomberg = _extract_bloomberg_ticker(block_words)

    if entry_price is None:
        warnings.append(f"missing entry price: {name} ({isin})")

    return ParsedHolding(
        isin=isin,
        name=name,
        asset_type=asset_type,
        quantity=qty,
        entry_price=entry_price,
        entry_currency=currency,
        entry_date=entry_date,
        current_price=current_price,
        current_value_base_ccy=market_value,
        bloomberg_ticker=bloomberg,
        metadata={
            "raw": block_text[:400],
            "current_date": current_date.isoformat() if current_date else None,
        },
    )


# ---------- per-field extractors -----------------------------------------------

def _find_qty(block, currency: str) -> Decimal | None:
    """Quantity is always a small integer in the qty column (x < 145)."""
    candidates: list[tuple[float, int]] = []
    for w in block:
        if w["text"] == currency:
            continue
        cleaned = w["text"].replace("'", "").replace(",", "")
        if not _INT_RE.match(cleaned):
            continue
        n = int(cleaned)
        if n == 0 or n > 99999:
            continue
        if w["x0"] < COL_QTY_MAX_X:
            candidates.append((w["x0"], n))
    if not candidates:
        return None
    # Leftmost wins; if multiple, take the topmost
    candidates.sort()
    return Decimal(str(candidates[0][1]))


def _extract_isin_from_tokens(block) -> str | None:
    """Token-based ISIN extraction — robust to embedded spaces.

    Concatenate each contiguous run of 1-4 tokens (skipping whitespace) and
    test if the result is a 12-char ISIN-shaped string (2 letters + 10 alphanumerics
    with the last one being a digit).
    """
    # Only consider tokens in the ISIN column or close to it (x ~ 280-450)
    tokens = [w["text"] for w in block if w["x0"] < 500]
    n = len(tokens)
    for i in range(n):
        for length in (1, 2, 3, 4):
            cand = "".join(tokens[i:i + length]).upper()
            if (len(cand) == 12 and cand[:2].isalpha()
                    and cand[2:].isalnum() and cand[-1].isdigit()):
                # ISIN country codes are real 2-letter ISO codes; avoid false
                # positives like 'NA12345678910' from random text.
                if cand[:2] in _ISO_COUNTRY_2LETTER:
                    return cand
    return None


def _extract_dates(block) -> tuple[date | None, date | None]:
    """Pick entry + current date by x-column, not text order.

    Entry date sits in the Einstandskurs column (x ≈ 460-510),
    current date sits in the Aktueller Kurs column (x ≈ 510-560).
    Pdfplumber sometimes returns slightly different `top` values for visually
    aligned tokens, so a pure (top, x) sort can flip them — x-bounding fixes that.
    """
    # Date columns are slightly wider than the price columns — include
    # x ≥ 440 so we don't miss '03.06.2019' (typically at x ≈ 455).
    DATE_COL_MIN = 440
    DATE_SPLIT = 505  # midpoint between entry-date and current-date columns
    DATE_COL_MAX = 580
    entry_candidates: list[tuple[float, date]] = []
    current_candidates: list[tuple[float, date]] = []
    for w in block:
        m = _DATE_RE.fullmatch(w["text"])
        if not m:
            continue
        d, mo, y = m.groups()
        try:
            dt = date(int(y), int(mo), int(d))
        except ValueError:
            continue
        if DATE_COL_MIN <= w["x0"] < DATE_SPLIT:
            entry_candidates.append((w["top"], dt))
        elif DATE_SPLIT <= w["x0"] <= DATE_COL_MAX:
            current_candidates.append((w["top"], dt))
    entry_candidates.sort()
    current_candidates.sort()
    entry = entry_candidates[0][1] if entry_candidates else None
    current = current_candidates[0][1] if current_candidates else None
    return entry, current


def _extract_prices(block, qty: Decimal) -> tuple[Decimal | None, Decimal | None]:
    """Entry and current prices live in the price column (x in [680, 880])
    and on the topmost row of the block. They look like '47.1285' / '109.6000'.
    """
    candidates: list[tuple[float, float, Decimal]] = []  # (top, x, value)
    for w in block:
        if not (COL_PRICE_MIN_X < w["x0"] < COL_PRICE_MAX_X):
            continue
        v = _parse_decimal(w["text"])
        if v is None:
            continue
        if Decimal("0.05") < v < Decimal("100000") and v != qty:
            candidates.append((w["top"], w["x0"], v))
    if not candidates:
        return None, None
    candidates.sort()  # top-first, then leftmost

    # Heuristic: the first row of price candidates has [entry, current].
    # Group by top (within 4px), pick the first group, take the two leftmost.
    first_y = candidates[0][0]
    first_row = [c for c in candidates if abs(c[0] - first_y) < 5]
    first_row.sort(key=lambda c: c[1])  # by x
    entry = first_row[0][2] if len(first_row) >= 1 else None
    current = first_row[1][2] if len(first_row) >= 2 else None
    return entry, current


def _extract_market_value(block, qty: Decimal,
                          entry_price: Decimal | None,
                          current_price: Decimal | None) -> Decimal | None:
    """Market value (in base currency) lives in the 'Kurswert' column."""
    candidates: list[Decimal] = []
    for w in block:
        if not (COL_MARKET_MIN_X <= w["x0"] <= COL_MARKET_MAX_X):
            continue
        v = _parse_decimal(w["text"])
        if v is None:
            continue
        if v in {qty, entry_price, current_price}:
            continue
        candidates.append(v)
    return max(candidates) if candidates else None


def _extract_name(block, qty: Decimal, currency: str, isin: str | None) -> str:
    """Asset name = tokens in the name column on the topmost row of the block.
    Skip percentages, decimal numbers, and ticker-fragment tokens."""
    name_zone = [
        w for w in block
        if COL_NAME_MIN_X < w["x0"] < COL_NAME_MAX_X
        and w["text"] != currency
        and not _NUM_TOKEN_RE.match(w["text"])
        and not w["text"].endswith("%")
    ]
    if not name_zone:
        return "?"
    name_zone.sort(key=lambda w: (w["top"], w["x0"]))
    top_y = name_zone[0]["top"]
    first_line = [w for w in name_zone if abs(w["top"] - top_y) < 5]
    first_line.sort(key=lambda w: w["x0"])
    return " ".join(w["text"] for w in first_line).strip() or "?"


def _extract_bloomberg_ticker(block) -> str | None:
    """Find the Bloomberg ticker in the ISIN/Valor/Bloomberg/GICS column.

    The Bloomberg line sits below the ISIN+Valor numbers in the same x-band,
    e.g. for Amazon::

        US0231351067   <- ISIN
        645156         <- Valor (ignored — usually pure digits)
        AMZN UW        <- Bloomberg ticker  ← what we want
        Nicht-Basis... <- GICS sector

    Pattern: an alpha-only token (1-6 chars, uppercase) immediately followed
    by a known 2-letter exchange code on the same row (within ~4px of `top`).

    Returns the joined ticker like 'AMZN UW' or None when no match. The bare
    ticker is exposed via `ParsedHolding.ticker`; downstream `transactions.symbol`
    uses that as the preferred identifier.
    """
    isin_col = [w for w in block if COL_BLBG_MIN_X <= w["x0"] <= COL_BLBG_MAX_X]
    isin_col.sort(key=lambda w: (w["top"], w["x0"]))
    for i in range(len(isin_col) - 1):
        a, b = isin_col[i], isin_col[i + 1]
        if abs(a["top"] - b["top"]) > 4:
            continue
        # OCR sometimes lowercases the leading letter (`sDZ` instead of `SDZ`,
        # same pathology as `cH...` for ISINs). Up-case after token-grab and
        # validate only that it is alpha-only of plausible ticker length.
        head = a["text"].upper()
        tail = b["text"].upper()
        if not (1 <= len(head) <= 6 and head.isalpha()):
            continue
        if not (len(tail) == 2 and tail.isalpha()):
            continue
        if tail not in _BLOOMBERG_EXCHANGE_CODES:
            continue
        return f"{head} {tail}"
    return None


def _guess_asset_type(text: str) -> str:
    low = text.lower()
    if "anleihe" in low or "bond" in low:
        return "bond"
    if "etf" in low or "fonds" in low:
        return "etf"
    return "stock"


def _parse_decimal(s: str) -> Decimal | None:
    """Robust Decimal parse for LGT Swiss-format numbers.

    LGT uses apostrophe as thousands separator and dot as decimal. OCR
    sometimes adds stray commas (e.g. 26',655.31), or substitutes letters
    for digits (A->0, O->0, l/I->1).
    """
    cleaned = s.strip().lstrip("\'" + chr(34) + "`")
    cleaned = (cleaned.replace("'", "")
                       .replace(" ", "")
                       .replace(" ", ""))
    cleaned = (
        cleaned.replace("O", "0").replace("o", "0")
               .replace("l", "1").replace("I", "1")
               .replace("A", "0")
    )
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    if not re.match(r"^-?\d+(?:\.\d+)?$", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _dedup_holdings(holdings: list[ParsedHolding]) -> list[ParsedHolding]:
    seen: set[str] = set()
    out = []
    for h in holdings:
        key = (h.isin or h.name).upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


# ---------- konten (cash) section ----------------------------------------------

def _parse_konten_page(page, warnings: list[str]) -> list[ParsedCashPosition]:
    text = page.extract_text() or ""
    if "Konten (Liquidität)" not in text and "Callgelder (Liquidität)" not in text:
        return []
    out: list[ParsedCashPosition] = []

    # Konten table — '0046437.035 LI46 ... 192.09 1.000000 192.09 0.06 %' followed by 'EUR Konto' / 'USD Konto'
    konten_re = re.compile(
        r"(\d{7}\.\d{3})\s+(LI\d+(?:\s+\d+){4,})\s+([\d',.]+)\s+\d+\.\d+\s+[\d',.]+\s+\d+\.\d+\s*%"
    )
    for m in konten_re.finditer(text):
        account = m.group(1)
        bal = _parse_decimal(m.group(3))
        if bal is None:
            continue
        # Currency is on the next line as 'EUR Konto' / 'USD Konto'
        tail = text[m.end(): m.end() + 80]
        cm = re.search(r"\b([A-Z]{3})\s+Konto", tail)
        ccy = cm.group(1) if cm else "EUR"
        out.append(ParsedCashPosition(
            account=account, currency=ccy, balance=bal,
            metadata={"iban": re.sub(r"\s+", "", m.group(2))},
        ))

    # Callgelder — 'usD 61'000.00 Termineinlage - Tagesgeld'
    for m in re.finditer(
        r"\b([A-Za-z]{3})\s+([\d',.]+)\s+(Termineinlage|Festgeld|Tagesgeld|Spareinlage|Callgeld)",
        text,
    ):
        ccy = m.group(1).upper()
        if ccy not in SUPPORTED_CURRENCIES:
            continue
        bal = _parse_decimal(m.group(2))
        if bal is None:
            continue
        out.append(ParsedCashPosition(
            account=f"call:{ccy}",
            currency=ccy,
            balance=bal,
            metadata={"product": m.group(3)},
        ))
    return out


# ---------- ISO country codes (for ISIN sanity checking) -----------------------

# Subset of ISO 3166-1 alpha-2 codes that show up in ISINs. Big enough not to
# false-negative real ISINs, restrictive enough to filter junk like 'NAxxx'.
_ISO_COUNTRY_2LETTER = frozenset({
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AR", "AT", "AU", "AW",
    "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL", "BM",
    "BN", "BO", "BR", "BS", "BT", "BW", "BY", "BZ", "CA", "CD", "CF", "CG",
    "CH", "CI", "CK", "CL", "CM", "CN", "CO", "CR", "CU", "CV", "CW", "CY",
    "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC", "EE", "EG", "ER", "ES",
    "ET", "FI", "FJ", "FM", "FR", "GA", "GB", "GD", "GE", "GG", "GH", "GI",
    "GL", "GM", "GN", "GQ", "GR", "GT", "GU", "GW", "GY", "HK", "HN", "HR",
    "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IQ", "IR", "IS", "IT", "JE",
    "JM", "JO", "JP", "KE", "KG", "KH", "KM", "KN", "KP", "KR", "KW", "KY",
    "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS", "LT", "LU", "LV", "LY",
    "MA", "MC", "MD", "ME", "MG", "MH", "MK", "ML", "MM", "MN", "MO", "MR",
    "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA", "NE", "NG", "NI", "NL",
    "NO", "NP", "NR", "NZ", "OM", "PA", "PE", "PG", "PH", "PK", "PL", "PR",
    "PS", "PT", "PY", "QA", "RO", "RS", "RU", "RW", "SA", "SB", "SC", "SD",
    "SE", "SG", "SI", "SK", "SL", "SM", "SN", "SO", "SR", "ST", "SV", "SY",
    "SZ", "TC", "TD", "TG", "TH", "TJ", "TM", "TN", "TO", "TR", "TT", "TV",
    "TW", "TZ", "UA", "UG", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VN",
    "VU", "WS", "XS",  # XS = Eurobonds
    "YE", "ZA", "ZM", "ZW",
})
