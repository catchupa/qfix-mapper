"""Tests for the Eton Shirts scraper extraction functions."""
import json
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from eton_scraper import (
    _extract_json_ld_product,
    _extract_product_id,
    _extract_product_name,
    _extract_description,
    _extract_color,
    _extract_material,
    _extract_image_url,
    _extract_clothing_type,
    scrape_product,
)


def _make_eton_html(
    name="Vit poplinskjorta",
    description="Ikonisk businesskjorta i bomullspoplin",
    sku="2567-00-10",
    material="100% Bomull",
    color="Vit",
    breadcrumbs=None,
    image_url="https://api.etonshirts.com/v1/retail/image/1080/white-poplin-shirt.webp",
):
    product_data = {
        "@context": "https://schema.org",
        "@type": "ProductGroup",
        "@id": "white-poplin-shirt",
        "name": name,
        "description": description,
        "brand": "Eton",
        "sku": sku,
        "material": material,
        "color": color,
    }
    product_json = json.dumps(product_data)

    breadcrumb_json = ""
    if breadcrumbs:
        bc_data = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": name}
                for i, name in enumerate(breadcrumbs)
            ],
        }
        breadcrumb_json = f'<script type="application/ld+json">{json.dumps(bc_data)}</script>'

    og_tag = ""
    if image_url:
        og_tag = f'<meta property="og:image" content="{image_url}"/>'

    return f"""
    <html><head>
    <script type="application/ld+json">{product_json}</script>
    {breadcrumb_json}
    {og_tag}
    </head><body>
    <h1>{name}</h1>
    </body></html>
    """


# ── JSON-LD extraction ───────────────────────────────────────────────────

def test_extract_json_ld_product():
    soup = BeautifulSoup(_make_eton_html(), "html.parser")
    product = _extract_json_ld_product(soup)
    assert product is not None
    assert product["@type"] == "ProductGroup"
    assert product["name"] == "Vit poplinskjorta"


def test_extract_json_ld_product_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_json_ld_product(soup) is None


# ── Product ID extraction ────────────────────────────────────────────────

def test_extract_product_id():
    data = {"sku": "2567-00-10"}
    assert _extract_product_id(data) == "2567-00-10"


def test_extract_product_id_missing():
    assert _extract_product_id(None) is None
    assert _extract_product_id({}) is None


# ── Product name extraction ──────────────────────────────────────────────

def test_extract_product_name():
    soup = BeautifulSoup(_make_eton_html(), "html.parser")
    product = _extract_json_ld_product(soup)
    assert _extract_product_name(product, soup) == "Vit poplinskjorta"


def test_extract_product_name_fallback_h1():
    soup = BeautifulSoup("<html><body><h1>Fallback Name</h1></body></html>", "html.parser")
    assert _extract_product_name(None, soup) == "Fallback Name"


# ── Description extraction ───────────────────────────────────────────────

def test_extract_description():
    soup = BeautifulSoup(_make_eton_html(), "html.parser")
    product = _extract_json_ld_product(soup)
    assert _extract_description(product, soup) == "Ikonisk businesskjorta i bomullspoplin"


def test_extract_description_missing():
    assert _extract_description(None, None) is None


# ── Color extraction ─────────────────────────────────────────────────────

def test_extract_color():
    data = {"color": "Vit"}
    assert _extract_color(data) == "Vit"


def test_extract_color_missing():
    assert _extract_color(None) is None


# ── Material extraction ──────────────────────────────────────────────────

def test_extract_material():
    data = {"material": "100% Bomull"}
    assert _extract_material(data) == "100% Bomull"


def test_extract_material_missing():
    assert _extract_material(None) is None


# ── Image URL extraction ─────────────────────────────────────────────────

def test_extract_image_url():
    soup = BeautifulSoup(_make_eton_html(), "html.parser")
    url = _extract_image_url(soup)
    assert url == "https://api.etonshirts.com/v1/retail/image/1080/white-poplin-shirt.webp"


def test_extract_image_url_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_image_url(soup) is None


# ── Clothing type extraction ─────────────────────────────────────────────

def test_extract_clothing_type_from_breadcrumbs():
    html = _make_eton_html(breadcrumbs=["Hem", "Businesskjortor", "Vita skjortor", "Vit poplinskjorta"])
    soup = BeautifulSoup(html, "html.parser")
    ct = _extract_clothing_type(soup)
    assert ct == "Businesskjortor > Vita skjortor"


def test_extract_clothing_type_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_clothing_type(soup) is None


# ── Full scrape_product ──────────────────────────────────────────────────

def test_scrape_product():
    html = _make_eton_html(breadcrumbs=["Hem", "Businesskjortor", "Vita skjortor", "Vit poplinskjorta"])
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    result = scrape_product("https://www.etonshirts.com/se/sv/product/white-poplin-shirt", session=mock_session)
    assert result is not None
    assert result["product_id"] == "2567-00-10"
    assert result["product_name"] == "Vit poplinskjorta"
    assert result["brand"] == "Eton"
    assert result["material_composition"] == "100% Bomull"
    assert result["color"] == "Vit"
    assert result["clothing_type"] == "Businesskjortor > Vita skjortor"
    assert result["category"] == "businesskjortor"


def test_scrape_product_no_id():
    html = "<html><body><h1>No product</h1></body></html>"
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    result = scrape_product("https://www.etonshirts.com/se/sv/product/unknown", session=mock_session)
    assert result is None
