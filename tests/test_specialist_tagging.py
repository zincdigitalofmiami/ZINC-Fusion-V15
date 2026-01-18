"""
Tests for Specialist Tagging Module

Run with: pytest tests/test_specialist_tagging.py -v
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fusion.tagging import (
    BIG_11_SPECIALISTS,
    DUAL_TAG_KEYWORDS,
    SPECIALIST_KEYWORDS,
    classify_specialists,
)
from fusion.tagging.specialist_classifier import (
    classify_specialists_with_scores,
    validate_specialists,
)


class TestConstants:
    """Tests for Big-11 specialist constants."""

    def test_big_11_count(self):
        """Big-11 should have exactly 11 specialists."""
        assert len(BIG_11_SPECIALISTS) == 11

    def test_big_11_names(self):
        """Big-11 should contain expected specialist names."""
        expected = {
            "crush",
            "china",
            "fx",
            "fed",
            "tariff",
            "energy",
            "biofuel",
            "palm",
            "volatility",
            "substitutes",
            "trump_effect",
        }
        assert set(BIG_11_SPECIALISTS) == expected

    def test_dual_tag_keywords_exist(self):
        """DUAL_TAG_KEYWORDS should have entries."""
        assert len(DUAL_TAG_KEYWORDS) > 0
        assert "trade deal" in DUAL_TAG_KEYWORDS


class TestKeywordCoverage:
    """Tests for keyword dictionary completeness."""

    def test_all_specialists_have_keywords(self):
        """Each specialist should have at least 5 keywords."""
        for specialist in BIG_11_SPECIALISTS:
            assert specialist in SPECIALIST_KEYWORDS, f"Missing keywords for {specialist}"
            assert (
                len(SPECIALIST_KEYWORDS[specialist]) >= 5
            ), f"{specialist} has only {len(SPECIALIST_KEYWORDS[specialist])} keywords (need >= 5)"

    def test_no_tariff_trump_overlap(self):
        """Tariff and trump_effect should not share keywords (use DUAL_TAG for shared)."""
        tariff_kw = set(SPECIALIST_KEYWORDS["tariff"])
        trump_kw = set(SPECIALIST_KEYWORDS["trump_effect"])
        overlap = tariff_kw & trump_kw
        assert len(overlap) == 0, f"Unexpected keyword overlap: {overlap}"

    def test_keywords_are_lowercase(self):
        """All keywords should be lowercase for consistent matching."""
        for specialist, keywords in SPECIALIST_KEYWORDS.items():
            for kw in keywords:
                assert kw == kw.lower(), f"Keyword '{kw}' in {specialist} is not lowercase"


class TestClassifySpecialists:
    """Tests for the main classification function."""

    def test_empty_text_returns_general(self):
        """Empty text should return ['general']."""
        assert classify_specialists("") == ["general"]
        assert classify_specialists(None) == ["general"]

    def test_unknown_text_returns_general(self):
        """Text with no keywords should return ['general']."""
        assert classify_specialists("Weather is nice today") == ["general"]
        assert classify_specialists("Hello world") == ["general"]

    def test_single_specialist_match(self):
        """Text with one specialist keyword should return that specialist."""
        result = classify_specialists("USDA reports strong soybean crush margins")
        assert "crush" in result

    def test_multiple_specialist_match(self):
        """Text with multiple specialist keywords should return all matches."""
        result = classify_specialists("China imports crude oil from Brazil")
        assert "china" in result
        assert "energy" in result

    def test_dual_tag_trade_deal(self):
        """Trade deal keywords should trigger both tariff and trump_effect."""
        result = classify_specialists("China trade deal announced")
        assert "china" in result
        assert "tariff" in result
        assert "trump_effect" in result

    def test_case_insensitive(self):
        """Classification should be case-insensitive."""
        result1 = classify_specialists("CHINA imports soybeans")
        result2 = classify_specialists("china imports soybeans")
        result3 = classify_specialists("China Imports Soybeans")
        assert set(result1) == set(result2) == set(result3)

    def test_no_duplicates(self):
        """Each specialist should appear at most once."""
        result = classify_specialists("china chinese beijing shanghai")
        assert result.count("china") == 1


class TestSpecificSpecialists:
    """Tests for specific specialist classification."""

    def test_crush_keywords(self):
        """Crush specialist keywords should match correctly."""
        assert "crush" in classify_specialists("soybean meal prices rise")
        assert "crush" in classify_specialists("crush margin improves")
        assert "crush" in classify_specialists("NOPA report shows strong processing")

    def test_china_keywords(self):
        """China specialist keywords should match correctly."""
        assert "china" in classify_specialists("Beijing buys soybeans")
        assert "china" in classify_specialists("COFCO increases imports")
        assert "china" in classify_specialists("African swine fever impacts herd")

    def test_fx_keywords(self):
        """FX specialist keywords should match correctly."""
        assert "fx" in classify_specialists("Dollar strengthens against real")
        assert "fx" in classify_specialists("Exchange rate volatility increases")
        assert "fx" in classify_specialists("DXY hits new highs")

    def test_fed_keywords(self):
        """Fed specialist keywords should match correctly."""
        assert "fed" in classify_specialists("Federal Reserve raises rates")
        assert "fed" in classify_specialists("FOMC meeting minutes released")
        assert "fed" in classify_specialists("Powell speaks on monetary policy")

    def test_tariff_keywords(self):
        """Tariff specialist keywords should match correctly."""
        assert "tariff" in classify_specialists("Section 301 tariffs imposed")
        assert "tariff" in classify_specialists("WTO rules against duties")
        assert "tariff" in classify_specialists("Anti-dumping investigation launched")

    def test_energy_keywords(self):
        """Energy specialist keywords should match correctly."""
        assert "energy" in classify_specialists("Crude oil prices surge")
        assert "energy" in classify_specialists("OPEC cuts production")
        assert "energy" in classify_specialists("Diesel demand increases")

    def test_biofuel_keywords(self):
        """Biofuel specialist keywords should match correctly."""
        assert "biofuel" in classify_specialists("Biodiesel production ramps up")
        assert "biofuel" in classify_specialists("RFS mandate announced")
        assert "biofuel" in classify_specialists("D4 RIN prices spike")
        assert "biofuel" in classify_specialists("45Z credit impacts market")

    def test_palm_keywords(self):
        """Palm specialist keywords should match correctly."""
        assert "palm" in classify_specialists("Palm oil exports from Malaysia")
        assert "palm" in classify_specialists("MPOB data shows production drop")
        assert "palm" in classify_specialists("Indonesia sets export levy")

    def test_volatility_keywords(self):
        """Volatility specialist keywords should match correctly."""
        assert "volatility" in classify_specialists("VIX spikes on uncertainty")
        assert "volatility" in classify_specialists("Options premiums increase")
        assert "volatility" in classify_specialists("Flight to safety observed")

    def test_substitutes_keywords(self):
        """Substitutes specialist keywords should match correctly."""
        assert "substitutes" in classify_specialists("Canola prices competitive")
        assert "substitutes" in classify_specialists("Sunflower oil production rises")
        assert "substitutes" in classify_specialists("Used cooking oil demand surges")

    def test_trump_effect_keywords(self):
        """Trump effect specialist keywords should match correctly."""
        assert "trump_effect" in classify_specialists("White House announces policy")
        assert "trump_effect" in classify_specialists("Executive order signed")
        assert "trump_effect" in classify_specialists("Policy uncertainty index rises")
        assert "trump_effect" in classify_specialists("DOGE cuts spending")


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_classify_with_scores(self):
        """classify_specialists_with_scores should return match counts."""
        scores = classify_specialists_with_scores("China trade policy affects soybean crush")
        assert "china" in scores
        assert "tariff" in scores
        assert "crush" in scores
        assert all(isinstance(v, int) for v in scores.values())

    def test_validate_specialists(self):
        """validate_specialists should filter invalid tags."""
        tags = ["crush", "invalid", "china", "fake", "general"]
        valid = validate_specialists(tags)
        assert "crush" in valid
        assert "china" in valid
        assert "general" in valid
        assert "invalid" not in valid
        assert "fake" not in valid


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_text(self):
        """Long text should still classify correctly."""
        long_text = "China " * 1000 + "trade deal " + "soybeans " * 500
        result = classify_specialists(long_text)
        assert "china" in result
        assert "tariff" in result  # from "trade deal"
        assert "trump_effect" in result  # from "trade deal"

    def test_special_characters(self):
        """Text with special characters should classify correctly."""
        result = classify_specialists("China's soybean imports up 25%!")
        assert "china" in result

    def test_multiline_text(self):
        """Multiline text should classify correctly."""
        text = """
        China announces new trade deal.
        USDA reports strong crush margins.
        Federal Reserve holds rates steady.
        """
        result = classify_specialists(text)
        assert "china" in result
        assert "crush" in result
        assert "fed" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
