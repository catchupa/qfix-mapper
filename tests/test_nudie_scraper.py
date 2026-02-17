"""Tests for the Nudie Jeans scraper extraction functions."""
import json
from unittest.mock import MagicMock
from bs4 import BeautifulSoup

from nudie_scraper import (
    _extract_json_ld_product,
    _extract_product_id,
    _extract_product_name,
    _extract_description,
    _extract_material_composition,
    _extract_color,
    _extract_brand,
    _extract_image_url,
    _extract_clothing_type,
    _extract_category_from_url,
    scrape_product,
)


def _make_nudie_html(
    name="Steady Eddie II Sand Storm",
    description="Regular fit jeans with a tapered leg",
    sku="115053",
    brand_name="Nudie Jeans",
    breadcrumbs=None,
    image_url="https://nudie.centracdn.net/client/dynamic/images/115053.jpg",
    composition="100% Cotton",
):
    product_data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "sku": sku,
        "brand": {"@type": "Brand", "name": brand_name},
    }
    if image_url:
        product_data["image"] = [image_url]
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

    # Simulate the Next.js RSC flight payload with pr_composition
    rsc_data = ""
    if composition:
        rsc_data = f'<script>self.__next_f.push([1, "{{\\"type\\":{{\\"name\\":\\"pr_composition\\",\\"isMulti\\":false}},\\"elements\\":[{{\\"key\\":\\"name\\",\\"kind\\":\\"INPUT\\",\\"value\\":\\"{composition}\\"}}]}}"])</script>'

    return f"""
    <html><head>
    <script type="application/ld+json">{product_json}</script>
    {breadcrumb_json}
    {og_tag}
    </head><body>
    <h1>{name}</h1>
    {rsc_data}
    </body></html>
    """


# ── JSON-LD extraction ───────────────────────────────────────────────────

def test_extract_json_ld_product():
    soup = BeautifulSoup(_make_nudie_html(), "html.parser")
    product = _extract_json_ld_product(soup)
    assert product is not None
    assert product["@type"] == "Product"
    assert product["name"] == "Steady Eddie II Sand Storm"


def test_extract_json_ld_product_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_json_ld_product(soup) is None


# ── Product ID extraction ────────────────────────────────────────────────

def test_extract_product_id():
    data = {"sku": "115053"}
    assert _extract_product_id(data) == "115053"


def test_extract_product_id_missing():
    assert _extract_product_id(None) is None
    assert _extract_product_id({}) is None


# ── Product name extraction ──────────────────────────────────────────────

def test_extract_product_name():
    soup = BeautifulSoup(_make_nudie_html(), "html.parser")
    product = _extract_json_ld_product(soup)
    assert _extract_product_name(product, soup) == "Steady Eddie II Sand Storm"


def test_extract_product_name_fallback_h1():
    soup = BeautifulSoup("<html><body><h1>Fallback Name</h1></body></html>", "html.parser")
    assert _extract_product_name(None, soup) == "Fallback Name"


# ── Description extraction ───────────────────────────────────────────────

def test_extract_description():
    soup = BeautifulSoup(_make_nudie_html(), "html.parser")
    product = _extract_json_ld_product(soup)
    assert _extract_description(product, soup) == "Regular fit jeans with a tapered leg"


def test_extract_description_missing():
    assert _extract_description(None, None) is None


# ── Material composition extraction ──────────────────────────────────────

def test_extract_material_composition():
    html = _make_nudie_html(composition="100% Cotton")
    assert _extract_material_composition(html) == "100% Cotton"


def test_extract_material_composition_multi():
    html = _make_nudie_html(composition="98% Cotton 2% Elastane")
    assert _extract_material_composition(html) == "98% Cotton 2% Elastane"


def test_extract_material_composition_missing():
    html = "<html><body>No composition here</body></html>"
    assert _extract_material_composition(html) is None


# ── Color extraction ─────────────────────────────────────────────────────

def test_extract_color_missing():
    # Nudie doesn't have a pr_color attribute, so color is None
    html = _make_nudie_html()
    assert _extract_color(html) is None


# ── Brand extraction ─────────────────────────────────────────────────────

def test_extract_brand():
    data = {"brand": {"@type": "Brand", "name": "Nudie Jeans"}}
    assert _extract_brand(data) == "Nudie Jeans"


def test_extract_brand_string():
    data = {"brand": "Nudie Jeans"}
    assert _extract_brand(data) == "Nudie Jeans"


def test_extract_brand_missing():
    assert _extract_brand(None) == "Nudie Jeans"


# ── Image URL extraction ─────────────────────────────────────────────────

def test_extract_image_url():
    soup = BeautifulSoup(_make_nudie_html(), "html.parser")
    product = _extract_json_ld_product(soup)
    assert _extract_image_url(product, soup) == "https://nudie.centracdn.net/client/dynamic/images/115053.jpg"


def test_extract_image_url_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_image_url(None, soup) is None


# ── Clothing type extraction ─────────────────────────────────────────────

def test_extract_clothing_type_from_breadcrumbs():
    html = _make_nudie_html(breadcrumbs=["Home", "Men's Jeans", "Regular Tapered", "Steady Eddie II Sand Storm"])
    soup = BeautifulSoup(html, "html.parser")
    ct = _extract_clothing_type(soup)
    assert ct == "Men's Jeans > Regular Tapered"


def test_extract_clothing_type_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_clothing_type(soup) is None


# ── Category from URL ────────────────────────────────────────────────────

def test_extract_category_jeans():
    assert _extract_category_from_url("https://nudiejeans.com/en-SE/product/grim-tim-jeans") == "jeans"


def test_extract_category_jacket():
    assert _extract_category_from_url("https://nudiejeans.com/en-SE/product/barney-worker-jacket") == "jackets"


def test_extract_category_shirt():
    assert _extract_category_from_url("https://nudiejeans.com/en-SE/product/casual-shirt") == "shirts"


def test_extract_category_unknown():
    assert _extract_category_from_url("https://nudiejeans.com/en-SE/product/something") is None


# ── Full scrape_product ──────────────────────────────────────────────────

def test_scrape_product():
    html = _make_nudie_html(breadcrumbs=["Home", "Men's Jeans", "Regular Tapered", "Steady Eddie II Sand Storm"])
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    result = scrape_product("https://www.nudiejeans.com/en-SE/product/steady-eddie-ii-sand-storm", session=mock_session)
    assert result is not None
    assert result["product_id"] == "115053"
    assert result["product_name"] == "Steady Eddie II Sand Storm"
    assert result["brand"] == "Nudie Jeans"
    assert result["material_composition"] == "100% Cotton"
    assert result["clothing_type"] == "Men's Jeans > Regular Tapered"
    assert result["category"] == "men's jeans"


def test_scrape_product_no_id():
    html = "<html><body><h1>No product</h1></body></html>"
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    result = scrape_product("https://www.nudiejeans.com/en-SE/product/unknown", session=mock_session)
    assert result is None
