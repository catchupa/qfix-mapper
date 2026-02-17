"""Tests for the Lindex scraper extraction functions."""
import json

from lindex_scraper import (
    _extract_json_ld,
    _parse_nuxt_data,
    _extract_product_urls,
    _extract_category_links,
)


def _make_lindex_json_ld(
    name="Krinklad midi klänning",
    description="Midiklänning med rynk, v-ringning.",
    product_id="3010022-7258",
    image="https://i8.amplience.net/s/Lindex/3010022_7258_ProductVariant",
):
    ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "productID": product_id,
        "image": image,
    }
    return f'<script type="application/ld+json">{json.dumps(ld)}</script>'


def _make_nuxt_data(
    style_id="3010022",
    name="Krinklad midi klänning",
    description="Midiklänning med rynk, v-ringning.",
    composition="70% viskos 30% polyamid",
    color_name="Light Dusty Pink",
    color_group="Rosa",
):
    """Build a __NUXT_DATA__ array matching the real dict-based format.

    The real Nuxt 3 format uses a flat array where some entries are dicts
    with keys pointing to value indices in the same array.
    """
    # Values stored at specific indices
    arr = [
        "filler0",       # 0
        style_id,        # 1
        name,            # 2
        description,     # 3
        composition,     # 4
        color_name,      # 5
        color_group,     # 6
        {                # 7: product dict with index refs
            "styleId": 1,
            "name": 2,
            "description": 3,
            "composition": 4,
            "colorName": 5,
            "colorGroup": 6,
        },
    ]
    return f'<script type="application/json" id="__NUXT_DATA__">{json.dumps(arr)}</script>'


def _make_lindex_html(
    name="Krinklad midi klänning",
    description="Midiklänning med rynk, v-ringning.",
    product_id="3010022-7258",
    composition="70% viskos 30% polyamid",
    color_name="Light Dusty Pink",
    color_group="Rosa",
    image="https://i8.amplience.net/s/Lindex/3010022_7258_ProductVariant",
):
    json_ld = _make_lindex_json_ld(name, description, product_id, image)
    nuxt = _make_nuxt_data(
        style_id=product_id.split("-")[0],
        name=name,
        description=description,
        composition=composition,
        color_name=color_name,
        color_group=color_group,
    )
    return f"<html><head>{json_ld}</head><body>{nuxt}</body></html>"


# ── JSON-LD extraction ───────────────────────────────────────────────────

def test_extract_json_ld():
    html = _make_lindex_html()
    ld = _extract_json_ld(html)
    assert ld is not None
    assert ld["name"] == "Krinklad midi klänning"
    assert ld["productID"] == "3010022-7258"


def test_extract_json_ld_missing():
    assert _extract_json_ld("<html><body></body></html>") is None


# ── NUXT_DATA parsing ────────────────────────────────────────────────────

def test_parse_nuxt_data():
    html = _make_lindex_html()
    data = _parse_nuxt_data(html)
    assert data["styleId"] == "3010022"
    assert data["name"] == "Krinklad midi klänning"
    assert data["composition"] == "70% viskos 30% polyamid"
    assert data["colorName"] == "Light Dusty Pink"
    assert data["colorGroup"] == "Rosa"


def test_parse_nuxt_data_missing():
    data = _parse_nuxt_data("<html><body></body></html>")
    assert data == {}


def test_parse_nuxt_data_no_lining():
    """Product dict without optional liningComp key should omit it from result."""
    nuxt_arr = [
        "3010022",         # 0
        "Test product",    # 1
        "TestColor",       # 2
        "100% bomull",     # 3
        {                  # 4: product dict - has required keys but no liningComp
            "styleId": 0,
            "name": 1,
            "colorName": 2,
            "composition": 3,
        },
    ]
    html = f'<html><script type="application/json" id="__NUXT_DATA__">{json.dumps(nuxt_arr)}</script></html>'
    data = _parse_nuxt_data(html)
    assert data["styleId"] == "3010022"
    assert data["composition"] == "100% bomull"
    assert "liningComp" not in data


def test_parse_nuxt_data_with_indexed_refs():
    """Test that indexed references in dict values are resolved."""
    nuxt_arr = [
        "3010022",         # 0
        "100% bomull",     # 1
        "Short product",   # 2
        "Blue",            # 3
        {                  # 4: product dict with index refs
            "styleId": 0,
            "composition": 1,
            "name": 2,
            "colorName": 3,
        },
    ]
    html = f'<html><script type="application/json" id="__NUXT_DATA__">{json.dumps(nuxt_arr)}</script></html>'
    data = _parse_nuxt_data(html)
    assert data["styleId"] == "3010022"
    assert data["composition"] == "100% bomull"


# ── Product URL extraction ───────────────────────────────────────────────

def test_extract_product_urls():
    html = '''
    <a href="/se/p/3010022-7258-krinklad-midi-klanning">Product 1</a>
    <a href="/se/p/3002544-1172-bla-lilja-vadderad">Product 2</a>
    <a href="/se/dam/klanningar">Category</a>
    '''
    urls = _extract_product_urls(html)
    assert len(urls) == 2
    assert "https://www.lindex.com/se/p/3010022-7258" in urls
    assert "https://www.lindex.com/se/p/3002544-1172" in urls


def test_extract_product_urls_empty():
    urls = _extract_product_urls("<html><body>No products</body></html>")
    assert len(urls) == 0


# ── Category link extraction ─────────────────────────────────────────────

def test_extract_category_links():
    html = '''
    <a href="/se/dam/klanningar">Klänningar</a>
    <a href="/se/dam/byxor">Byxor</a>
    <a href="/se/barn/toppar?hl=sv">Toppar</a>
    <a href="/se/p/12345-67890">Product</a>
    <a href="/se/checkout/">Checkout</a>
    '''
    links = _extract_category_links(html)
    assert "/se/dam/klanningar" in links
    assert "/se/dam/byxor" in links
    assert "/se/barn/toppar" in links
    assert "/se/p/12345-67890" not in links
    assert "/se/checkout/" not in links


def test_extract_category_links_empty():
    links = _extract_category_links("<html><body>No links</body></html>")
    assert len(links) == 0
