"""Tests for the oeffentlichevergabe.de export scraper."""

import io
import json
import zipfile
from unittest.mock import Mock

import pytest

from scrapers._oeffentlichevergabe import OeffentlicheVergabeScraper
from utils.keywords import KeywordMatcher


def _zip(files: dict) -> bytes:
    """Build an in-memory ZIP from {name: content}."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _package(release: dict) -> str:
    return json.dumps({"releases": [release]})


JEN_RELEASE = {
    "id": "25855874",
    "date": "2026-09-24T07:01:39Z",
    "tag": ["tender"],
    "buyer": {"name": "JEN Jülicher Entsorgungsgesellschaft für Nuklearanlagen mbH"},
    "tender": {
        "title": "Sachverständigenleistung Fassmessanlagen",
        "procurementMethodDetails": "Public announcement",
        "items": [{"deliveryAddress": {"locality": "Jülich"}}],
        "lots": [{"id": "LOT-0000", "title": "Sachverständigenleistung Fassmessanlagen"}],
    },
}

JEN_EFORMS = (
    "<ns7:ContractNotice><ns5:TenderSubmissionDeadlinePeriod>"
    "<ns3:EndDate>2026-10-08+02:00</ns3:EndDate>"
    "</ns5:TenderSubmissionDeadlinePeriod></ns7:ContractNotice>"
)


@pytest.fixture
def scraper():
    return OeffentlicheVergabeScraper({}, Mock())


def test_parses_jen_notice(scraper):
    deadlines = scraper._parse_deadlines(_zip({"25855874-1.xml": JEN_EFORMS}))
    results = scraper._parse_ocds_export(
        _zip({"25855874-1.json": _package(JEN_RELEASE)}), deadlines
    )

    assert len(results) == 1
    result = results[0]
    assert result.portal == "oeffentlichevergabe"
    assert result.vergabe_id == "25855874"
    assert result.titel == "Sachverständigenleistung Fassmessanlagen"
    assert result.naechste_frist == "08.10.2026"
    assert result.veroeffentlicht == "24.09.2026"
    assert result.ausfuehrungsort == "Jülich"
    assert result.link == (
        "https://oeffentlichevergabe.de/ui/de/search/details"
        "?noticeId=25855874&lotId=LOT-0000"
    )


def test_jen_notice_matches_all_keywords(scraper):
    results = scraper._parse_ocds_export(_zip({"a.json": _package(JEN_RELEASE)}), {})
    matcher = KeywordMatcher("config/Suchbegriffe_ALL.txt")

    assert matcher.matches(results[0].titel)


def test_skips_award_notices(scraper):
    award = dict(JEN_RELEASE, tag=["award"])
    untagged_award = dict(JEN_RELEASE, tag=[], awards=[{"id": "1"}])

    assert scraper._parse_release(award, "", Mock()) == []
    assert scraper._parse_release(untagged_award, "", Mock()) == []


def test_lot_titles_appended_to_title(scraper):
    tender = dict(
        JEN_RELEASE["tender"],
        title="Rahmenvertrag IT",
        lots=[
            {"id": "LOT-0001", "title": "Rahmenvertrag IT - Los 1"},
            {"id": "LOT-0002", "title": "Rahmenvertrag IT - Strahlenschutzberatung"},
            {"id": "LOT-0003", "title": "Los 3"},
        ],
    )
    results = scraper._parse_release(dict(JEN_RELEASE, tender=tender), "", Mock())

    assert results[0].titel == "Rahmenvertrag IT | Strahlenschutzberatung"
