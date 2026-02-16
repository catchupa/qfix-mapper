"""Tests for vision classification mapping (no actual API calls)."""
from unittest.mock import patch, MagicMock

from vision import classify_and_map


@patch("vision.identify_product")
def test_classify_and_map_trousers(mock_identify):
    mock_identify.return_value = {
        "clothing_type": "Trousers",
        "material": "Standard textile",
        "color": "Blue",
        "category": "Women's Clothing",
    }

    result = classify_and_map(b"fake image", "image/jpeg")

    assert result["classification"]["clothing_type"] == "Trousers"
    assert result["qfix"]["qfix_clothing_type"] == "Trousers"
    assert result["qfix"]["qfix_clothing_type_id"] == 174
    assert result["qfix"]["qfix_material"] == "Standard textile"
    assert result["qfix"]["qfix_material_id"] == 69
    assert result["qfix"]["qfix_url"] is not None


@patch("vision.identify_product")
def test_classify_and_map_jacket_leather(mock_identify):
    mock_identify.return_value = {
        "clothing_type": "Jacket",
        "material": "Leather/Suede",
        "color": "Brown",
        "category": "Men's Clothing",
    }

    result = classify_and_map(b"fake image", "image/jpeg")

    assert result["qfix"]["qfix_clothing_type"] == "Jacket"
    assert result["qfix"]["qfix_clothing_type_id"] == 173
    assert result["qfix"]["qfix_material"] == "Leather/Suede"
    assert result["qfix"]["qfix_material_id"] == 71
    assert result["qfix"]["qfix_subcategory"] == "Men's Clothing"


@patch("vision.identify_product")
def test_classify_and_map_unknown(mock_identify):
    mock_identify.return_value = {
        "clothing_type": "Other",
        "material": "Other/Unsure",
        "color": "Unknown",
        "category": "Women's Clothing",
    }

    result = classify_and_map(b"fake image", "image/jpeg")

    assert result["qfix"]["qfix_clothing_type"] == "Other"
    assert result["qfix"]["qfix_clothing_type_id"] == 105
