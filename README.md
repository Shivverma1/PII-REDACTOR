# PII Redaction Tool

Reads a document (PDF or plain text) and produces a redacted copy in which every
detected piece of personally identifiable information is replaced with a
**realistic fake** — not a black box. The same original value always maps to the
same fake (`Kushal Subbayya Hegde` is the same fake person on page 1 and page 90),
and re-running the tool reproduces identical output.

## Quick start

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm

python redact.py "Red Herring Prospectus.pdf" --mapping pii_mapping.json
python -m pytest tests/          # run the test suite
```

Deliverables in this folder:

| File | What it is |
|---|---|
| `pii_redactor/` | source code (package) |
| `Red Herring Prospectus.redacted.txt` | the redacted output |
| `pii_mapping.json` | audit trail: every original → fake pair (generated at runtime via `--mapping`; deliberately not committed, since it contains the original PII) |
| `tests/test_detectors.py` | unit tests (26, all passing) |

## Approach

A **hybrid pipeline** — regex for structured PII, NER for names — because neither
alone is sufficient:

1. **Structured detectors (regex + validation)** for emails, phone numbers, SSNs,
   credit cards (Luhn-checksum validated), IPv4 addresses (octet-validated),
   dates of birth (only in an explicit "Date of Birth / born on / DOB" context),
   URLs, Indian CINs and PANs. Addresses are anchored on Indian 6-digit PIN codes
   and expanded to the enclosing address phrase, guarded by address vocabulary so
   bare 6-digit figures don't match.
2. **spaCy NER (`en_core_web_sm`)** proposes person and organisation names, then
   plausibility filters and a domain noise-list remove its frequent
   financial-vocabulary mislabels ("Equity Shares" is not a person).
   Pattern harvesting adds what NER structurally misses: corporate-suffix names
   ("… Private Limited", "… LLP", "… Family Trust"), slash-separated contact
   lists ("Eric Bacha/ Sachin Gawade"), surname matches ("Vijay Hegde" once any
   "… Hegde" is known), and stand-alone brand tokens ("Nuvama", "KSH").
3. **Whitespace-tolerant propagation**: every confirmed name is then matched
   everywhere, case-insensitively, allowing arbitrary whitespace *between any two
   characters* — PDF table extraction splits words mid-token
   ("Kushal \nSubba \nyya Hegde"), so ordinary word matching silently leaks names.
4. **Overlap resolution** keeps the longest span (ties broken by type priority)
   and trims, rather than drops, partially-overlapped spans — an address starting
   inside a company-name match is still redacted.
5. **Replacement** via Faker, seeded per-value with an MD5 hash → consistent and
   deterministic. Format is preserved where it matters: phones keep the `+91`
   and digit grouping, companies keep their legal suffix, ALL-CAPS originals get
   ALL-CAPS fakes, fake IPs come from the RFC 5737 documentation range.

### Explicit precision choices (what is deliberately KEPT)

* **Public institutions and statutes** — SEBI, RBI, the stock exchanges,
  "Companies Act", regulator domains (`sebi.gov.in`, `bseindia.com`) — are not
  private PII; redacting them would make a prospectus meaningless.
* **Ordinary document dates** (board resolutions, certificate dates) — only dates
  in an explicit birth context are treated as DOBs.
* **Financial figures, share counts, page numbers** — phone/card candidates must
  carry a `+91`/label anchor or pass the Luhn checksum, so numbers like
  "4,200.00 million" never match.
* Order/ticket-style reference numbers are kept (none carrying personal identity
  appear in this document); CIN/PAN *are* redacted because they map directly to
  a legal entity or person.

## Evaluation

Four independent checks (the first three are automated):

1. **Unit tests** (`tests/`): positive fixtures for every PII type — including
   SSN, credit card, IP and DOB, which don't occur in this document but are
   required by the assignment — plus negative fixtures (share counts are not
   credit cards, `www.sebi.gov.in` is kept, invalid IP octets rejected) and
   pipeline properties (consistency, determinism, format preservation).
2. **Residual scan** (runs automatically after redaction): re-runs all structured
   detectors over the *output*; anything found that the tool didn't generate
   itself is reported as a leak. Final run: **0 leftovers**.
3. **Known-terms audit**: the output was grep-audited against 40+ manually
   collected real values from the source (promoter surnames, the company
   secretary, emails, phone fragments, PINs, village names, CINs, advisor firms)
   — all removed — and against a keep-list of functional terms (SEBI, Companies
   Act, "Anchor Investor", "Registered Broker"…) — all preserved.
4. **Manual spot-check** of the output around high-density regions (cover page,
   management tables, banker/registrar blocks).

Final run over the 128-page prospectus: **1,162 redactions, 518 unique values**
(companies 777, persons 212, addresses 66, emails 50, phones 36, URLs 26, CINs 6).

## Tradeoffs and known limitations

* **PDF extraction is the hard part.** Table cells shred text (single letters per
  line, emails split around the `@`). The tolerant patterns recover the cases
  observed here, but a fully-shredded token in some other document could still
  slip through; the residual scan exists to catch exactly that.
* **Output is plain text**, not a re-laid-out PDF — faithful in-place PDF
  replacement with fakes of different lengths is a typesetting problem out of
  scope here.
* **False-positive pressure**: brand-token propagation ("Nuvama") is guarded by a
  strong-suffix requirement, a generic-word blocklist and a document-frequency
  ceiling; without those, generic words ("Anchor", "Escrow") get redacted — we
  observed and fixed exactly that during development.
* **False-negative pressure**: names NER never proposes anywhere (e.g. a house
  name like "Pushpakamal") are only caught if a structural pattern covers them —
  here the address expander does. A larger NER model (`en_core_web_trf`) would
  raise recall at ~20× the runtime.
* The small spaCy model is English-only; other scripts (Devanagari names) would
  need a multilingual model.

## Extending to a new PII type

1. Add a member to `PIIType` (`pii_redactor/types.py`).
2. Add a detector class in `pii_redactor/detectors/` and register it in
   `detectors/__init__.py` (subclass `Detector`, implement `detect()`).
3. Add a `_gen_<type>` method to `FakeFactory` (`anonymizer.py`).
4. Add a fixture to `tests/test_detectors.py`.

Nothing in the engine, CLI or evaluation changes.
