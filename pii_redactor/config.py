"""Every tunable of the redaction pipeline in one place.

Policy decisions (what is deliberately KEPT) live here so they are easy to
review and change:

* Public institutions -- regulators, exchanges, statutes -- are not private
  PII; redacting "SEBI" or "Companies Act" would make a prospectus
  meaningless. See ``ORG_ALLOWLIST_RE`` and ``PUBLIC_DOMAINS``.
* Ordinary document dates (board meetings, certificates) are kept; only
  dates in an explicit birth context are treated as dates of birth.
* Financial figures, share counts and page numbers are never phone/card
  candidates thanks to context anchors and checksum validation.
"""

from __future__ import annotations

import re

from .types import PIIType

# --------------------------------------------------------------------------
# Overlap priority: when two detected spans overlap, the longer span wins;
# on equal length, the LOWER number here wins (structured identifiers are
# more precise than NER guesses).
# --------------------------------------------------------------------------
PRIORITY: dict[PIIType, int] = {
    PIIType.EMAIL: 0,
    PIIType.URL: 1,
    PIIType.PHONE: 2,
    PIIType.CIN: 3,
    PIIType.PAN: 4,
    PIIType.SSN: 5,
    PIIType.CREDIT_CARD: 6,
    PIIType.IP_ADDRESS: 7,
    PIIType.DATE_OF_BIRTH: 8,
    PIIType.ADDRESS: 9,
    PIIType.COMPANY: 10,
    PIIType.PERSON: 11,
}

# --------------------------------------------------------------------------
# Kept on purpose: domains of public institutions (regulators, exchanges,
# statute registries, reference-data providers).
# --------------------------------------------------------------------------
PUBLIC_DOMAINS: tuple[str, ...] = (
    "sebi.gov.in",
    "rbi.org.in",
    "bseindia.com",
    "nseindia.com",
    "mca.gov.in",
    "fbil.org.in",
    "oanda.com",
)

# Kept on purpose: public bodies, statutes and market infrastructure.
ORG_ALLOWLIST_RE = re.compile(
    r"(?i)securities and exchange board|reserve bank|\bsebi\b|\brbi\b|"
    r"bse limited|national stock exchange|stock exchange|companies act|"
    r"government|ministry|income tax|goods and services|registrar of companies"
)

# --------------------------------------------------------------------------
# NER noise: financial-prospectus vocabulary that the small spaCy model
# frequently mislabels as a person or organisation.
# --------------------------------------------------------------------------
NER_NOISE: frozenset[str] = frozenset({
    "offer", "equity", "shares", "share", "bid", "bids", "bidders", "price",
    "promoter", "promoters", "director", "directors", "company", "prospectus",
    "board", "registrar", "email", "mutual", "funds", "allotment", "syndicate",
    "investors", "portion", "proceeds", "statements", "circular", "branch",
    "facility", "facilities", "office", "taluka", "complex", "east", "west",
    "report", "act", "regulations", "rupees", "amount", "draft", "red",
    "herring", "corrigenda", "upi", "asba", "qib", "nii", "rii", "term",
    "broker", "brokers", "stockbrokers",
})

# Additional words that never occur inside a real PERSON name (they are
# legitimate inside company names, so they must not go in NER_NOISE).
PERSON_NOISE: frozenset[str] = frozenset({
    "broker", "brokers", "stockbrokers", "bill", "finance", "limited",
    "registered", "centre", "centres", "formerly", "known", "bank",
    "private", "public", "trust", "industries", "enterprises",
})

# Generic words that must never be treated as a stand-alone company brand
# when propagating the first token of a company name ("Nuvama", "Trilegal").
BRAND_BLOCK: frozenset[str] = frozenset({
    "national", "federal", "state", "indian", "india", "reserve", "central",
    "standard", "united", "first", "stock", "exchange", "small", "general",
    "securities", "bank", "export", "import", "life", "insurance", "housing",
    "development", "industrial", "finance", "investment", "capital", "asset",
    "trustee", "family", "private", "public", "limited", "village", "taluka",
    "registered", "corporate", "mumbai", "pune", "delhi", "kolkata", "chennai",
    "maharashtra", "think", "supa", "form", "challan",
    # generic corporate / prospectus vocabulary that may lead a company name
    # but never identifies one on its own
    "companies", "business", "escrow", "refund", "anchor", "credit", "audit",
    "issue", "sale", "fresh", "independent", "international", "legal",
    "management", "market", "profit", "qualified", "risk", "risks", "working",
    "statutory", "retail", "revision", "venture", "cloud", "designated",
    "diluted", "domestic", "financial", "governance", "group", "running",
    "switchgear", "date", "details", "offer", "total", "formerly", "known",
})

# spaCy model used for person / organisation recognition.
SPACY_MODEL = "en_core_web_sm"
