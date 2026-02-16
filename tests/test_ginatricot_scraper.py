"""Tests for Gina Tricot scraper extraction functions."""
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from ginatricot_scraper import (
    _extract_product_id,
    _extract_category,
    _extract_json_ld_product,
    _extract_product_name,
    _extract_description,
    _extract_brand,
    _extract_color,
    _extract_material,
    _extract_clothing_type_from_url,
    scrape_product,
)


# ── URL-based extraction ──────────────────────────────────────────────────

def test_extract_product_id():
    url = "https://www.ginatricot.com/se/klader/kjolar/langkjolar/structure-maxi-skirt-225549000"
    assert _extract_product_id(url) == "225549000"


def test_extract_product_id_with_slash():
    url = "https://www.ginatricot.com/se/klader/jeans/momjeans/dagny-mom-jeans-867151159/"
    assert _extract_product_id(url) == "867151159"


def test_extract_product_id_short_number():
    """IDs shorter than 6 digits should not match."""
    url = "https://www.ginatricot.com/se/klader/jeans/12345"
    assert _extract_product_id(url) is None


def test_extract_product_id_no_number():
    url = "https://www.ginatricot.com/se/klader/jeans/momjeans"
    assert _extract_product_id(url) is None


def test_extract_category_klader():
    assert _extract_category("https://www.ginatricot.com/se/klader/jeans/mom-jeans-123456789") == "klader"


def test_extract_category_accessoarer():
    assert _extract_category("https://www.ginatricot.com/se/accessoarer/solglasogon/sunglasses-123456789") == "accessoarer"


def test_extract_category_unknown():
    assert _extract_category("https://www.ginatricot.com/se/other/stuff") is None


# ── JSON-LD extraction (HTML-encoded) ─────────────────────────────────────

def test_extract_json_ld_product(sample_ginatricot_html):
    html = sample_ginatricot_html(name="Test Product")
    soup = BeautifulSoup(html, "html.parser")
    product = _extract_json_ld_product(soup)
    assert product is not None
    assert product["name"] == "Test Product"
    assert product["@type"] == "Product"


def test_extract_json_ld_product_missing():
    html = "<html><body></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_json_ld_product(soup) is None


def test_extract_product_name(sample_ginatricot_html):
    html = sample_ginatricot_html(name="Structure maxi skirt")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_product_name(soup) == "Structure maxi skirt"


def test_extract_product_name_fallback_h1():
    html = "<html><body><h1>Fallback Title</h1></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_product_name(soup) == "Fallback Title"


def test_extract_description(sample_ginatricot_html):
    html = sample_ginatricot_html(description="En fin kjol")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_description(soup) == "En fin kjol"


def test_extract_description_missing(sample_ginatricot_html):
    html = sample_ginatricot_html(description=None)
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_description(soup) is None


def test_extract_brand(sample_ginatricot_html):
    html = sample_ginatricot_html(brand="Gina Tricot")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_brand(soup) == "Gina Tricot"


def test_extract_brand_as_dict(sample_ginatricot_html):
    """Brand can be a string or dict — test string form (GT uses string)."""
    html = sample_ginatricot_html(brand="Gina Tricot")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_brand(soup) == "Gina Tricot"


# ── Color extraction ──────────────────────────────────────────────────────

def test_extract_color_strips_code(sample_ginatricot_html):
    html = sample_ginatricot_html(color="Black (9000)")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_color(soup) == "Black"


def test_extract_color_no_code(sample_ginatricot_html):
    html = sample_ginatricot_html(color="Offwhite dest")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_color(soup) == "Offwhite dest"


def test_extract_color_missing(sample_ginatricot_html):
    html = sample_ginatricot_html(color=None)
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_color(soup) is None


# ── Material extraction ───────────────────────────────────────────────────

def test_extract_material(sample_ginatricot_html):
    html = sample_ginatricot_html(material="Bomull 57%, Polyamid 42%, Elastan 1%")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_material(soup) == "Bomull 57%, Polyamid 42%, Elastan 1%"


def test_extract_material_null(sample_ginatricot_html):
    html = sample_ginatricot_html(material=None)
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_material(soup) is None


# ── Clothing type from URL ────────────────────────────────────────────────

def test_clothing_type_from_url():
    url = "https://www.ginatricot.com/se/klader/kjolar/langkjolar/structure-maxi-skirt-225549000"
    assert _extract_clothing_type_from_url(url) == "kjolar > langkjolar"


def test_clothing_type_from_url_accessoarer():
    url = "https://www.ginatricot.com/se/accessoarer/solglasogon/sunglasses-123456789"
    assert _extract_clothing_type_from_url(url) == "solglasogon"


def test_clothing_type_from_url_shallow():
    url = "https://www.ginatricot.com/se/klader/jeans/mom-jeans-123456789"
    assert _extract_clothing_type_from_url(url) == "jeans"


# ── Full scrape_product with mocked HTTP ──────────────────────────────────

@patch("ginatricot_scraper.requests.get")
def test_scrape_product(mock_get, sample_ginatricot_html):
    html = sample_ginatricot_html(
        name="Structure maxi skirt",
        description="Lågmidjad långkjol",
        brand="Gina Tricot",
        color="Black (9000)",
        material="Bomull 57%, Polyamid 42%, Elastan 1%",
    )
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    url = "https://www.ginatricot.com/se/klader/kjolar/langkjolar/structure-maxi-skirt-225549000"
    result = scrape_product(url)

    assert result is not None
    assert result["product_id"] == "225549000"
    assert result["product_name"] == "Structure maxi skirt"
    assert result["category"] == "klader"
    assert result["clothing_type"] == "kjolar > langkjolar"
    assert result["material_composition"] == "Bomull 57%, Polyamid 42%, Elastan 1%"
    assert result["description"] == "Lågmidjad långkjol"
    assert result["color"] == "Black"
    assert result["brand"] == "Gina Tricot"
    assert result["product_url"] == url


@patch("ginatricot_scraper.requests.get")
def test_scrape_product_no_id(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = "<html><body></body></html>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = scrape_product("https://www.ginatricot.com/se/klader/jeans/momjeans")
    assert result is None
