"""Tests for keyword boundary matching."""

import pytest

from utils.keywords import KeywordMatcher


def _matcher(tmp_path, *keywords: str) -> KeywordMatcher:
    path = tmp_path / "keywords.txt"
    path.write_text("\n".join(keywords) + "\n", encoding="utf-8")
    return KeywordMatcher(str(path))


@pytest.mark.parametrize("keyword", ["AI", "AI ", " AI", " AI "])
@pytest.mark.parametrize(
    "text",
    [
        "AI",
        "Einsatz von AI im Betrieb",
        "AI-gestützte Auswertung",
        "Beratung (AI) und Analyse",
        "Projekt: AI, ML und Data",
        "Plattform für AI",
    ],
)
def test_short_keyword_matches_standalone(tmp_path, keyword, text):
    assert _matcher(tmp_path, keyword).matches(text)


@pytest.mark.parametrize("keyword", ["AI", "AI ", " AI", " AI "])
@pytest.mark.parametrize(
    "text",
    [
        "Planungsleistungen nach HOAI für Neubau",
        "Planung gemäß HOAI",
        "Ausführung ab Mai 2027",
        "Training von AIs",
    ],
)
def test_short_keyword_ignores_embedded(tmp_path, keyword, text):
    assert not _matcher(tmp_path, keyword).matches(text)


def test_long_keyword_substring(tmp_path):
    matcher = _matcher(tmp_path, "Rückbau")
    assert matcher.matches("Produktionsrückbau")
    assert matcher.matches("Rückbaukonzept")


def test_long_keyword_markers(tmp_path):
    assert _matcher(tmp_path, " Lager").matches("Neue Lagerhalle")
    assert not _matcher(tmp_path, " Lager").matches("Endlager Konrad")
    assert _matcher(tmp_path, "Lager ").matches("Endlager Konrad")
    assert not _matcher(tmp_path, "Lager ").matches("Neue Lagerhalle")
    assert _matcher(tmp_path, " Lager ").matches("Planung (Lager)")
    assert not _matcher(tmp_path, " Lager ").matches("Endlager")


def test_ba_keywords_do_not_match_hoai():
    matcher = KeywordMatcher("config/Suchbegriffe_BA.txt")
    assert matcher.get_matching_keyword("Objektplanung nach HOAI") is None
    assert matcher.matches("KI-gestützte Dokumentenanalyse")
