"""
Module 2 — Quantity Extractor
Extracts and normalizes numerical quantities with units from Wikipedia revision text.
"""

import re
import spacy


nlp = spacy.load("en_core_web_sm")



MULTIPLIERS = {
    "million": 1e6,
    "billion": 1e9,
    "trillion": 1e12,
    "thousand": 1e3,
    "hundred": 1e2,
}


UNIT_ALIASES = {
    "km²": "m2", "km2": "m2", "square km": "m2", "square kilometres": "m2",
    "square kilometers": "m2", "sq km": "m2",
    "m²": "m2", "m2": "m2", "square meters": "m2", "square metres": "m2",
    "km": "m", "kilometre": "m", "kilometres": "m", "kilometer": "m", "kilometers": "m",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gram": "g", "grams": "g",
    "ton": "kg", "tonne": "kg", "tonnes": "kg", "tons": "kg",
    "%": "percent", "percent": "percent", "percentage": "percent",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "people": "people", "population": "people", "inhabitants": "people", "residents": "people",
    "year": "years", "years": "years", "yr": "years", "yrs": "years",
}

UNIT_CONVERSIONS = {
    "m2": 1,          # base: m²
    "m": 1,           # base: m
    "km": 1000,       # → m
    "kg": 1,          # base: kg
    "g": 0.001,       # → kg
    "ton": 1000,      # → kg (metric tonne)
}


_NUM = r"[\d,]+(?:\.\d+)?"  # e.g. 1,300 or 1.3
_MULT = r"(?:\s*(?:million|billion|trillion|thousand|hundred))?"
_RANGE = rf"({_NUM})\s*[–—\-~to]+\s*({_NUM})"  # e.g. 100–200

QUANTITY_PATTERN = re.compile(
    rf"""
    (?P<currency>\$|USD\s)?          # optional currency prefix
    (?P<range_lo>{_NUM})\s*[–—\-~]\s*(?P<range_hi>{_NUM})  # range: 100–200
    |
    (?P<currency2>\$|USD\s)?         # optional currency prefix (single value)
    (?P<number>{_NUM})               # the number
    (?P<multiplier>{_MULT})          # optional multiplier word
    \s*
    (?P<unit>
        km²|km2|km|m²|m2|           # area / length
        kg|g\b|ton(?:ne)?s?|        # mass
        \%|percent(?:age)?|         # percent
        USD|dollars?|               # explicit USD
        (?:square\s+(?:km|kilometers?|kilometres?|meters?|metres?))|
        (?:sq\.?\s*km)|
        people|population|inhabitants?|residents?|
        years?|yrs?|age
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Detect trailing multiplier after a plain number (e.g. "1.3 million people")
TRAILING_MULT_UNIT = re.compile(
    rf"({_NUM})\s*(million|billion|trillion|thousand)?\s*"
    r"(km²|km2|km|m²|m2|kg|g\b|ton(?:ne)?s?|\%|percent(?:age)?|USD|dollars?|"
    r"(?:square\s+(?:km|kilometers?|kilometres?|meters?|metres?))|(?:sq\.?\s*km)|"
    r"people|population|inhabitants?|residents?|years?|yrs?|age)?",
    re.IGNORECASE,
)

# Year pattern — used to filter out bare years
YEAR_PATTERN = re.compile(r"^(1[0-9]{3}|20[0-9]{2})$")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def extract_entities(text: str) -> list[dict]:

    doc = nlp(text)
    entities = []
    target_labels = {"CARDINAL", "QUANTITY", "MONEY", "PERCENT"}

    for ent in doc.ents:
        if ent.label_ not in target_labels:
            continue
        # Grab the full sentence containing this entity
        sentence = ent.sent.text.strip()
        entities.append({
            "span_text": ent.text,
            "label": ent.label_,
            "sentence": sentence,
            "start_char": ent.start_char,
            "end_char": ent.end_char,
        })
    return entities


def detect_unit(text: str) -> tuple[float | None, str | None, str]:
  
    text = text.strip()

    # Check for range first (e.g. "100–200 km")
    range_match = re.search(
        rf"({_NUM})\s*[–—\-~to]+\s*({_NUM})\s*"
        r"(km²|km2|km|m²|m2|kg|g\b|ton(?:ne)?s?|\%|percent(?:age)?|USD|dollars?|"
        r"(?:square\s+(?:km|kilometers?|kilometres?|meters?|metres?))|(?:sq\.?\s*km)|"
        r"people|population|inhabitants?|residents?|years?|yrs?|age)?",
        text, re.IGNORECASE
    )
    if range_match:
        lo = float(range_match.group(1).replace(",", ""))
        hi = float(range_match.group(2).replace(",", ""))
        avg = (lo + hi) / 2
        unit = range_match.group(3) or ""
        return avg, unit.strip() or None, text

    # Single value
    m = TRAILING_MULT_UNIT.search(text)
    if not m or not m.group(1):
        return None, None, text

    raw_num = m.group(1).replace(",", "")
    try:
        value = float(raw_num)
    except ValueError:
        return None, None, text

    multiplier_str = (m.group(2) or "").strip().lower()
    unit_str = (m.group(3) or "").strip()

    # Apply multiplier
    if multiplier_str in MULTIPLIERS:
        value *= MULTIPLIERS[multiplier_str]

    # Check for currency prefix in original text
    if re.search(r"\$|USD", text, re.IGNORECASE) and not unit_str:
        unit_str = "USD"

    return value, unit_str or None, text


def normalize_value(value: float, unit: str | None) -> tuple[float, str]:
    
    if unit is None:
        return value, "unknown"

    canonical = UNIT_ALIASES.get(unit.lower(), unit.lower())

    # Area: km² → m²
    if unit.lower() in ("km²", "km2", "square km", "sq km", "square kilometres",
                        "square kilometers"):
        return value * 1e6, "m2"

    # Length: km → m
    if unit.lower() in ("km", "kilometre", "kilometres", "kilometer", "kilometers"):
        return value * 1000, "m"

    # Mass: ton → kg
    if unit.lower() in ("ton", "tonne", "tonnes", "tons"):
        return value * 1000, "kg"

    # Mass: g → kg
    if unit.lower() in ("g", "gram", "grams"):
        return value * 0.001, "kg"

    # Percent → 0–1
    if canonical == "percent":
        return value / 100, "percent"

    return value, canonical


def _is_bare_year(span_text: str, label: str) -> bool:
    """Return True if the span looks like a standalone year (not age/duration)."""
    cleaned = span_text.strip().replace(",", "")
    if label in ("QUANTITY",):
        return False  # QUANTITY entities usually have units
    return bool(YEAR_PATTERN.match(cleaned))


def extract_quantities(text: str) -> list[dict]:
    
    entities = extract_entities(text)
    results = []
    seen_spans = set()  # deduplicate by (start_char, end_char)

    for ent in entities:
        span = ent["span_text"]
        key = (ent["start_char"], ent["end_char"])
        if key in seen_spans:
            continue
        seen_spans.add(key)

        # Skip bare years (e.g. "In 2020") unless it's a QUANTITY/age context
        if _is_bare_year(span, ent["label"]):
            continue

        # For PERCENT entities, inject % if missing
        if ent["label"] == "PERCENT" and "%" not in span and "percent" not in span.lower():
            span = span + "%"

        # For MONEY entities, inject $ if missing
        if ent["label"] == "MONEY" and not re.search(r"\$|USD", span, re.IGNORECASE):
            span = "$" + span

        raw_value, raw_unit, original = detect_unit(span)
        if raw_value is None:
            continue

        norm_value, norm_unit = normalize_value(raw_value, raw_unit)

        results.append({
            "value": norm_value,
            "unit": norm_unit,
            "original_text": ent["span_text"],
            "sentence": ent["sentence"],
            "entity_label": ent["label"],
        })

    return results

