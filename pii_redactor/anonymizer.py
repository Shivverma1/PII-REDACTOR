"""Fake-value generation: consistent, deterministic and format-preserving.

* **Consistent** -- the same original value always maps to the same fake,
  so cross-references inside the document stay readable
  ("Kushal Subbayya Hegde" is the same fake person on page 1 and page 90).
* **Deterministic** -- the Faker instance is seeded from a hash of the
  original value, so re-running the tool reproduces the same output.
* **Format-preserving** -- phone numbers keep their country code and digit
  grouping; company names keep their legal suffix; ALL-CAPS originals get
  ALL-CAPS fakes; IPs come from the RFC 5737 documentation range.
"""

from __future__ import annotations

import hashlib
import re

from faker import Faker

from .detectors.names import ORG_SUFFIX_RE
from .types import PIIType

_COMPANY_SUFFIXES = (
    "Private Limited", "Family Trust", "Limited", "LLP", "Ltd", "Trust",
    "Bank", "HUF", "Industries", "Electricals", "Enterprises", "Engineering",
)

_COMPANY_STEMS = ("Industries", "Enterprises", "Holdings", "Ventures", "Solutions")


class FakeFactory:
    """Maps original PII values to fake replacements.

    ``mapping`` accumulates every original -> fake pair for the audit file;
    ``generated_values()`` feeds the residual scan so the tool's own output
    is not mistaken for leaked PII.
    """

    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}
        self._cache: dict[tuple[PIIType, str], str] = {}

    def fake(self, pii_type: PIIType, original: str) -> str:
        """Return the (stable) fake replacement for *original*."""
        key = (pii_type, self._normalize(original))
        if key not in self._cache:
            self._cache[key] = self._generate(pii_type, original)
        replacement = self._match_case(original, self._cache[key])
        self.mapping[" ".join(original.split())] = replacement
        return replacement

    def generated_values(self) -> set[str]:
        """Normalised fakes produced so far (for the residual scan)."""
        return {self._normalize(value) for value in self.mapping.values()}

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).lower()

    @staticmethod
    def _match_case(original: str, fake: str) -> str:
        return fake.upper() if original.isupper() else fake

    @staticmethod
    def _seeded_faker(original: str) -> Faker:
        seed = int(hashlib.md5(original.encode()).hexdigest(), 16) % (2 ** 32)
        faker = Faker()
        faker.seed_instance(seed)
        return faker

    def _generate(self, pii_type: PIIType, original: str) -> str:
        generator = getattr(self, f"_gen_{pii_type.value.lower()}", None)
        if generator is None:
            raise ValueError(f"no fake generator for PII type {pii_type}")
        return generator(self._seeded_faker(self._normalize(original)), original)

    # -- one small generator per PII type ------------------------------

    def _gen_person(self, faker: Faker, original: str) -> str:
        return faker.name()

    def _gen_company(self, faker: Faker, original: str) -> str:
        suffix = ""
        for known in _COMPANY_SUFFIXES:
            if re.search(rf"\b{known}\b", original, re.IGNORECASE):
                suffix = " " + known
                break
        stem = f"{faker.last_name()} {faker.random_element(_COMPANY_STEMS)}"
        return stem + suffix

    def _gen_email(self, faker: Faker, original: str) -> str:
        return f"{faker.first_name().lower()}.{faker.last_name().lower()}@example.com"

    def _gen_phone(self, faker: Faker, original: str) -> str:
        """Replace digits in place, preserving formatting and the country
        code, so "+ 91 20 4505 3237" keeps its exact shape."""
        keep_country = original.lstrip().startswith("+")
        output, digit_index = [], 0
        for char in original:
            if char.isdigit():
                digit_index += 1
                if keep_country and digit_index <= 2:
                    output.append(char)
                else:
                    output.append(str(faker.random_digit()))
            else:
                output.append(char)
        return "".join(output)

    def _gen_address(self, faker: Faker, original: str) -> str:
        if len(original.split()) <= 2 and not any(c.isdigit() for c in original):
            return faker.city()  # a bare locality name, not a full address
        return (
            f"{faker.building_number()}, {faker.street_name()}, "
            f"{faker.city()} - {faker.random_int(100000, 999999)}, India"
        )

    def _gen_ssn(self, faker: Faker, original: str) -> str:
        return faker.ssn()

    def _gen_credit_card(self, faker: Faker, original: str) -> str:
        return faker.credit_card_number()

    def _gen_ip_address(self, faker: Faker, original: str) -> str:
        return f"192.0.2.{faker.random_int(1, 254)}"  # RFC 5737 TEST-NET-1

    def _gen_date_of_birth(self, faker: Faker, original: str) -> str:
        born = faker.date_of_birth(minimum_age=25, maximum_age=70)
        return born.strftime("%B %d, %Y")

    def _gen_cin(self, faker: Faker, original: str) -> str:
        return (
            f"U{faker.random_number(5, True):05d}XX"
            f"{faker.random_int(1980, 2020)}PLC{faker.random_number(6, True):06d}"
        )

    def _gen_pan(self, faker: Faker, original: str) -> str:
        letters = "".join(faker.random_uppercase_letter() for _ in range(5))
        return f"{letters}{faker.random_number(4, True):04d}{faker.random_uppercase_letter()}"

    def _gen_url(self, faker: Faker, original: str) -> str:
        return f"www.{faker.domain_word()}.example.com"
