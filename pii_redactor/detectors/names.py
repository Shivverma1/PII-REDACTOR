"""Person and company name detection.

Strategy (three layers, each feeding the next):

1. **spaCy NER** proposes PERSON and ORG entities. The small English model
   mislabels financial vocabulary constantly, so candidates are filtered
   through plausibility rules and a domain noise list.
2. **Pattern harvesting** adds what NER structurally misses: names with a
   corporate suffix ("... Private Limited", "... LLP", "... Family Trust"),
   slash-separated contact-person lists ("Eric Bacha/ Sachin Gawade"), and
   leading brand tokens ("Nuvama", "KSH") that reference a company alone.
3. **Whitespace-tolerant propagation** then finds EVERY occurrence of every
   confirmed name, case-insensitively and tolerating arbitrary whitespace
   between characters -- PDF table extraction splits words mid-token
   ("Kushal \\nSubba \\nyya Hegde"), so word-level search is not enough.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Iterable

from ..config import (
    BRAND_BLOCK, NER_NOISE, ORG_ALLOWLIST_RE, PERSON_NOISE, SPACY_MODEL,
)
from ..types import PIIType, Span
from .base import Detector, register

logger = logging.getLogger(__name__)

ORG_SUFFIX_RE = re.compile(
    r"\b((?:[A-Z0-9][\w&.\-']*\s+){1,6}"
    r"(?:Limited|Ltd\.?|LLP|Private\s+Limited|Pvt\.?\s+Ltd\.?|"
    r"Family\s+Trust|Trust|Bank(?:\s+Limited)?|&\s+(?:Co|Associates)\.?(?:\s+LLP)?|"
    r"HUF|Industries|Electricals|Enterprises|Engineering))\b"
)

# Contact-person lists like "Eric Bacha/ Sachin Gawade/ Pravin Teli" that
# slash-separation hides from the NER model.
SLASH_NAMES_RE = re.compile(
    r"\b[A-Z][a-z]+(?: [A-Z][a-z']+){1,2}(?:\s*/\s*[A-Z][a-z]+(?: [A-Z][a-z']+){1,2})+"
)


def plausible_person(name: str) -> bool:
    """2-4 purely alphabetic words, none of them domain noise."""
    words = name.replace(".", " ").split()
    if not 2 <= len(words) <= 4:
        return False
    if any(w.lower() in NER_NOISE or w.lower() in PERSON_NOISE for w in words):
        return False
    return all(word.replace("-", "").isalpha() for word in words)


def plausible_org(name: str) -> bool:
    """At least two words, no domain noise, and not a public institution."""
    if ORG_ALLOWLIST_RE.search(name):
        return False
    words = name.split()
    return len(words) >= 2 and not any(word.lower() in NER_NOISE for word in words)


@lru_cache(maxsize=1)
def _load_nlp():
    """Load the spaCy pipeline once per process (it costs ~2s and ~100MB;
    a long-lived server must not pay that per request)."""
    import spacy

    nlp = spacy.load(SPACY_MODEL, disable=["parser", "lemmatizer"])
    nlp.max_length = 1_000_000
    return nlp


@lru_cache(maxsize=None)
def _tolerant_pattern(name: str) -> re.Pattern:
    """Pattern matching *name* with arbitrary whitespace between ANY two
    characters, so names fragmented across table-cell line breaks match."""
    parts = []
    for char in " ".join(name.split()):
        parts.append(r"\s+" if char == " " else re.escape(char) + r"\s*")
    body = "".join(parts).removesuffix(r"\s*")
    return re.compile(r"\b" + body + r"\b", re.IGNORECASE)


class NameAndCompanyDetector(Detector):
    """Emits PERSON and COMPANY spans (see module docstring for strategy)."""

    pii_type = PIIType.PERSON

    def detect(self, text: str) -> Iterable[Span]:
        persons, orgs = self._ner_entities(text)
        persons |= self._slash_separated_names(text)
        persons |= self._surname_matches(text, persons)
        suffix_orgs = self._suffix_orgs(text)
        orgs |= suffix_orgs
        brands = self._brand_tokens(text, suffix_orgs)
        logger.info(
            "name detection: %d persons, %d organisations, %d brand tokens",
            len(persons), len(orgs), len(brands),
        )

        # Overlap resolution prefers longer spans, so a person name contained
        # in an organisation name ("Karunakar Hegde" inside "Karunakar Hegde
        # HUF") is replaced with the organisation mapping where the suffix is
        # present and with the person mapping elsewhere.
        yield from self._propagate(text, persons, PIIType.PERSON)
        yield from self._propagate(text, orgs, PIIType.COMPANY)
        for brand in sorted(brands):
            pattern = re.compile(r"\b" + re.escape(brand) + r"\b", re.IGNORECASE)
            for match in pattern.finditer(text):
                yield Span(match.start(), match.end(), PIIType.COMPANY, match.group())

    # -- layer 1: NER ----------------------------------------------------

    def _ner_entities(self, text: str) -> tuple[set[str], set[str]]:
        nlp = _load_nlp()
        nlp.max_length = max(nlp.max_length, len(text) + 1)
        doc = nlp(text)

        persons: set[str] = set()
        orgs: set[str] = set()
        for entity in doc.ents:
            clean = " ".join(entity.text.split())
            if entity.label_ == "PERSON" and plausible_person(clean):
                persons.add(clean)
            elif entity.label_ == "ORG" and plausible_org(clean):
                orgs.add(clean)
        return persons, orgs

    # -- layer 2: pattern harvesting --------------------------------------

    def _slash_separated_names(self, text: str) -> set[str]:
        names: set[str] = set()
        for match in SLASH_NAMES_RE.finditer(text):
            for part in match.group().split("/"):
                clean = " ".join(part.split())
                if plausible_person(clean):
                    names.add(clean)
        return names

    def _suffix_orgs(self, text: str) -> set[str]:
        orgs: set[str] = set()
        for match in ORG_SUFFIX_RE.finditer(text):
            clean = " ".join(match.group(1).split())
            if plausible_org(clean):
                orgs.add(clean)
        return orgs

    def _surname_matches(self, text: str, persons: set[str]) -> set[str]:
        """New person names built from a confirmed surname with a different
        first name ("Vijay Hegde" when only "Rajesh Hegde" was recognised)."""
        surnames = {
            person.split()[-1]
            for person in persons
            if len(person.split()[-1]) >= 4
            and person.split()[-1].lower() not in NER_NOISE
            and person.split()[-1].lower() not in PERSON_NOISE
        }
        found: set[str] = set()
        for surname in surnames:
            for match in re.finditer(
                rf"\b([A-Z][a-z]+)\s+{re.escape(surname)}\b", text
            ):
                candidate = f"{match.group(1)} {surname}"
                if plausible_person(candidate):
                    found.add(candidate)
        return found

    def _brand_tokens(self, text: str, suffix_orgs: set[str]) -> set[str]:
        """Leading tokens that reference a company on their own: all-caps
        acronyms ("KSH") and distinctive proper names ("Nuvama").

        Precision guards -- a generic word must never become a "brand":

        * only companies confirmed by a strong legal suffix qualify, never
          raw NER guesses ("Anchor Investors" must not yield "Anchor");
        * a blocklist of generic corporate vocabulary (``BRAND_BLOCK``);
        * a document-frequency ceiling: a token occurring very often in a
          128-page document is a common word, not a distinctive brand.
        """
        strong = re.compile(r"(?:Limited|Ltd\.?|LLP|Trust|HUF|Bank)$")
        brands: set[str] = set()
        for org in suffix_orgs:
            if not strong.search(org):
                continue
            first = org.split()[0].rstrip(".,")
            if first.lower() in NER_NOISE or first.lower() in BRAND_BLOCK:
                continue
            if first.isupper() and first.isalpha() and 2 <= len(first) <= 5:
                if len(re.findall(rf"\b{first}\b", text)) <= 100:
                    brands.add(first)
            elif first[:1].isupper() and first[1:].islower() and len(first) >= 5:
                if len(re.findall(rf"\b{first}\b", text, re.IGNORECASE)) <= 40:
                    brands.add(first)
        return brands

    # -- layer 3: propagation ---------------------------------------------

    def _propagate(
        self, text: str, names: set[str], pii_type: PIIType
    ) -> Iterable[Span]:
        for name in sorted(names, key=len, reverse=True):
            for match in _tolerant_pattern(name).finditer(text):
                yield Span(match.start(), match.end(), pii_type, match.group())


def register_all() -> None:
    register(NameAndCompanyDetector())
