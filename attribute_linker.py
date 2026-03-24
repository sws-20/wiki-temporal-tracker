"""
Module 3 — Attribute Linker
Links extracted quantities to the noun/attribute they describe
using spaCy dependency parsing.
"""

import spacy

nlp = spacy.load("en_core_web_sm")

# ---------------------------------------------------------------------------
# Vocabulary: canonical attribute → synonyms/related words
# ---------------------------------------------------------------------------

ATTRIBUTE_VOCAB = {
    "population": ["population", "inhabitants", "residents", "people", "citizens"],
    "area":       ["area", "size", "territory", "region", "surface", "extent", "km", "km2"],
    "gdp":        ["gdp", "economy", "output", "product", "income", "gross"],
    "price":      ["price", "cost", "fee", "charge", "rate", "fare", "tariff"],
    "net worth":  ["worth", "wealth", "assets", "fortune", "valuation", "value"],
    "revenue":    ["revenue", "sales", "earnings", "turnover", "profit", "income"],
    "height":     ["height", "tall", "altitude", "elevation", "meters", "feet"],
    "distance":   ["distance", "length", "span", "range", "km", "miles", "away"],
}

# Flat lookup: word → canonical attribute
_WORD_TO_ATTR: dict[str, str] = {}
for _attr, _synonyms in ATTRIBUTE_VOCAB.items():
    for _syn in _synonyms:
        _WORD_TO_ATTR[_syn.lower()] = _attr


# ---------------------------------------------------------------------------
# Dependency relations we traverse to find the head noun
# ---------------------------------------------------------------------------

# Relations where the number token IS the dependent (points up to its noun)
NUM_AS_DEP = {"nummod", "quantmod"}

# Relations where the number token IS the head (points down to a noun)
NUM_AS_HEAD = {"nsubj", "attr", "dobj", "pobj", "nsubjpass"}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _normalize_attribute(noun: str) -> str | None:
    """
    Match a raw noun string to the closest canonical attribute.
    Returns None if no match found.
    """
    noun_lower = noun.lower().strip()
    # Direct hit
    if noun_lower in _WORD_TO_ATTR:
        return _WORD_TO_ATTR[noun_lower]
    # Partial / substring match
    for word, attr in _WORD_TO_ATTR.items():
        if word in noun_lower or noun_lower in word:
            return attr
    return None


def _find_head_noun(token: spacy.tokens.Token) -> spacy.tokens.Token | None:
    """
    Given a numeric token, walk the dependency tree to find the noun it modifies.

    Strategy:
      1. If token is a nummod/quantmod dependent → head is the noun directly.
      2. If token's head is a preposition (prep) → go up one more level to the
         governing noun (e.g. "population of 1.4 billion": billion→of→population).
      3. If token is the head of nsubj/attr/dobj/pobj → the dependent is the noun.
      4. Walk up to parent if still unresolved.
    """
    head = token.head

    # Case 1: direct nummod (e.g. "1.4 billion people" → people)
    if token.dep_ in NUM_AS_DEP:
        return head

    # Case 2: number is pobj of a prep → go up to prep's head noun
    # e.g. "population of 1.4 billion": 1.4→billion(nummod)→of(prep)→population
    if head.dep_ == "pobj" or head.dep_ == "prep":
        return head.head

    # Case 3: number is the head of a noun dependent
    for child in token.children:
        if child.dep_ in NUM_AS_HEAD and child.pos_ in ("NOUN", "PROPN"):
            return child

    # Case 4: climb one level and try the head's head noun
    if head.pos_ in ("NOUN", "PROPN"):
        return head
    if head.head.pos_ in ("NOUN", "PROPN"):
        return head.head

    return None


def _get_noun_phrase(token: spacy.tokens.Token) -> str:
    """Return the full noun phrase (compound + noun) for a token."""
    parts = [t.text for t in token.subtree
             if t.dep_ in ("compound", "amod", "nmod") or t == token]
    return " ".join(parts) if parts else token.text


def find_quantities_in_doc(doc: spacy.tokens.Doc) -> list[spacy.tokens.Token]:
    """Return tokens that are numeric (NUM pos or part of a CARDINAL/QUANTITY entity)."""
    numeric_tokens = set()

    # From NER spans
    for ent in doc.ents:
        if ent.label_ in ("CARDINAL", "QUANTITY", "MONEY", "PERCENT"):
            # Use the root token of the span
            numeric_tokens.add(ent.root)

    # Also catch bare NUM tokens not caught by NER
    for token in doc:
        if token.pos_ == "NUM":
            numeric_tokens.add(token)

    return list(numeric_tokens)


def link_quantities(sentence: str) -> list[dict]:
    """
    Main function. Takes a sentence, finds all quantities, and links each
    to its canonical attribute via dependency parsing.

    Returns list of dicts:
        quantity   – the quantity text as it appears in the sentence
        attribute  – canonical attribute name (or raw noun if no vocab match)
        raw_noun   – the raw noun phrase found before normalization
        sentence   – the input sentence
    """
    doc = nlp(sentence)
    results = []
    seen = set()

    numeric_tokens = find_quantities_in_doc(doc)

    for token in numeric_tokens:
        # Get the full entity span text if this token belongs to one
        qty_text = token.text
        for ent in doc.ents:
            if ent.start <= token.i < ent.end:
                qty_text = ent.text
                break

        if qty_text in seen:
            continue
        seen.add(qty_text)

        head_noun = _find_head_noun(token)
        if head_noun is None:
            continue

        raw_noun = _get_noun_phrase(head_noun)
        attribute = _normalize_attribute(raw_noun) or _normalize_attribute(head_noun.lemma_)

        results.append({
            "quantity": qty_text,
            "attribute": attribute or head_noun.lemma_.lower(),
            "raw_noun": raw_noun,
            "sentence": sentence,
        })

    return results




def extract_and_link(sentence: str) -> list[tuple[str, str]]:
   
    return [(r["quantity"], r["attribute"]) for r in link_quantities(sentence)]


