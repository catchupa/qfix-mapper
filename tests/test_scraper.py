"""Tests for KappAhl scraper extraction functions."""
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from scraper import (
    _extract_product_id,
    _extract_category,
    _extract_product_name,
    _extract_description,
    _extract_brand,
    _extract_color,
    _extract_clothing_type,
    _extract_material,
    _extract_material_from_text,
    _extract_image_url,
    scrape_product,
)


# ── URL-based extraction ──────────────────────────────────────────────────

def test_extract_product_id_from_p_url():
    assert _extract_product_id("https://www.kappahl.com/sv-se/dam/jeans/p/131367") == "131367"


def test_extract_product_id_from_trailing_number():
    assert _extract_product_id("https://www.kappahl.com/sv-se/dam/jeans/bootcut/131367") == "131367"


def test_extract_product_id_from_trailing_slash():
    assert _extract_product_id("https://www.kappahl.com/sv-se/dam/jeans/bootcut/131367/") == "131367"


def test_extract_product_id_missing():
    assert _extract_product_id("https://www.kappahl.com/sv-se/dam/jeans/bootcut/") is None


def test_extract_category_dam():
    assert _extract_category("https://www.kappahl.com/sv-se/dam/jeans/131367") == "dam"


def test_extract_category_herr():
    assert _extract_category("https://www.kappahl.com/sv-se/herr/jeans/131367") == "herr"


def test_extract_category_barn():
    assert _extract_category("https://www.kappahl.com/sv-se/barn/byxor/12345") == "barn"


def test_extract_category_baby():
    assert _extract_category("https://www.kappahl.com/sv-se/baby/bodys/12345") == "baby"


def test_extract_category_unknown():
    assert _extract_category("https://www.kappahl.com/sv-se/other/stuff") is None


# ── JSON-LD extraction ────────────────────────────────────────────────────

def test_extract_product_name(sample_kappahl_html):
    html = sample_kappahl_html(name="Bootcut jeans high waist")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_product_name(soup) == "Bootcut jeans high waist"


def test_extract_product_name_fallback_h1():
    html = "<html><body><h1>Fallback Name</h1></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_product_name(soup) == "Fallback Name"


def test_extract_description(sample_kappahl_html):
    html = sample_kappahl_html(description="En klassisk jeans modell")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_description(soup) == "En klassisk jeans modell"


def test_extract_description_missing():
    html = "<html><body></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_description(soup) is None


def test_extract_brand(sample_kappahl_html):
    html = sample_kappahl_html(brand_name="Xlnt")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_brand(soup) == "Xlnt"


def test_extract_brand_missing():
    html = "<html><body></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_brand(soup) is None


# ── Color extraction ──────────────────────────────────────────────────────

def test_extract_color(sample_kappahl_html):
    html = sample_kappahl_html(color_text="Svart / enfärgad")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_color(soup) == "Svart / enfärgad"


def test_extract_color_strips_storlek_boundary(sample_kappahl_html):
    """Color text should stop at 'Storlek' boundary."""
    html = sample_kappahl_html(color_text="Blå melerad")
    soup = BeautifulSoup(html, "html.parser")
    color = _extract_color(soup)
    assert "Storlek" not in color
    assert "Blå melerad" == color


# ── Clothing type extraction ──────────────────────────────────────────────

def test_extract_clothing_type_from_breadcrumb(sample_kappahl_html):
    html = sample_kappahl_html(breadcrumbs=["Hem", "Dam", "Jeans", "Bootcut & flare"])
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_clothing_type(soup)
    assert result == "Jeans > Bootcut & flare"


def test_extract_clothing_type_missing():
    html = "<html><body></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_clothing_type(soup) is None


# ── Material extraction ───────────────────────────────────────────────────

def test_extract_material_from_text_basic():
    text = "Huvudmaterial: 75% Bomull, 21% Polyester, 4% Elastan"
    result = _extract_material_from_text(text)
    assert "75% Bomull" in result
    assert "21% Polyester" in result
    assert "4% Elastan" in result


def test_extract_material_from_text_no_match():
    assert _extract_material_from_text("No materials here") is None


def test_extract_material_from_script(sample_kappahl_html):
    html = sample_kappahl_html(material_desc="Huvudmaterial: 99% Bomull, 1% Elastan")
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_material(soup)
    assert "99% Bomull" in result
    assert "1% Elastan" in result


# ── Full scrape_product with mocked HTTP ──────────────────────────────────

def test_extract_image_url(sample_kappahl_html):
    html = sample_kappahl_html(image_url="https://static.kappahl.com/img/131367.jpg")
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_image_url(soup) == "https://static.kappahl.com/img/131367.jpg"


def test_extract_image_url_missing():
    html = "<html><body></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_image_url(soup) is None


@patch("scraper._download_image")
@patch("scraper.requests.get")
def test_scrape_product(mock_get, mock_dl, sample_kappahl_html):
    html = sample_kappahl_html(
        name="Bootcut jeans",
        description="Snygga jeans",
        brand_name="KappAhl",
        color_text="Svart",
        material_desc="Huvudmaterial: 98% Bomull, 2% Elastan",
    )
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = scrape_product("https://www.kappahl.com/sv-se/dam/jeans/bootcut/131367")

    assert result is not None
    assert result["product_id"] == "131367"
    assert result["product_name"] == "Bootcut jeans"
    assert result["category"] == "dam"
    assert result["description"] == "Snygga jeans"
    assert result["brand"] == "KappAhl"
    assert result["color"] == "Svart"
    assert "98% Bomull" in result["material_composition"]
    assert result["product_url"] == "https://www.kappahl.com/sv-se/dam/jeans/bootcut/131367"
    assert result["image_url"] == "https://static.kappahl.com/productimages/131367_f_4.jpg"


@patch("scraper._download_image")
@patch("scraper.requests.get")
def test_scrape_product_no_id(mock_get, mock_dl):
    mock_resp = MagicMock()
    mock_resp.text = "<html><body></body></html>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = scrape_product("https://www.kappahl.com/sv-se/dam/jeans/bootcut/")
    assert result is None
