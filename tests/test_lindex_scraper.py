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
    """Build a simplified __NUXT_DATA__ array with indexed references."""
    # Nuxt uses indexed references: keys at index i, value ref at i+1
    # We build a minimal array: [header, key, ref_idx, key, ref_idx, ..., val, val, ...]
    arr = [
        ["ShallowReactive", 1],  # 0: header
        {},                       # 1: data object marker
        "styleId",                # 2
        7,                        # 3: ref -> index 7
        "name",                   # 4
        8,                        # 5: ref -> index 8
        "description",            # 6
        style_id,                 # 7: styleId value
        name,                     # 8: name value
    ]
    desc_idx = len(arr)
    arr.append(description)       # 9: description value
    arr[6] = "description"
    # Need to insert ref for description
    arr.insert(7, desc_idx)
    # Shift indices
    # Let's just build it simply:
    arr = [
        ["ShallowReactive", 1],
        "styleId", style_id,
        "name", name,
        "description", description,
        "composition", composition,
        "colorName", color_name,
        "colorGroup", color_group,
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


def test_parse_nuxt_data_no_composition():
    nuxt_arr = [
        ["ShallowReactive", 1],
        "styleId", "3010022",
        "name", "Test product",
    ]
    html = f'<html><script type="application/json" id="__NUXT_DATA__">{json.dumps(nuxt_arr)}</script></html>'
    data = _parse_nuxt_data(html)
    assert data["styleId"] == "3010022"
    assert "composition" not in data


def test_parse_nuxt_data_with_indexed_refs():
    """Test that indexed references are resolved."""
    # Index: 0=header, 1=key, 2=ref(->5), 3=key, 4=ref(->6), 5=value, 6=value
    nuxt_arr = [
        ["ShallowReactive", 1],
        "styleId", 7,
        "composition", 8,
        "name", "Short product",
        "3010022",           # index 7
        "100% bomull",       # index 8
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
    <a href="/se/dam/klanningar/">Klänningar</a>
    <a href="/se/dam/byxor/">Byxor</a>
    <a href="/se/p/12345-67890">Product</a>
    <a href="/se/checkout/">Checkout</a>
    '''
    links = _extract_category_links(html)
    assert "/se/dam/klanningar/" in links
    assert "/se/dam/byxor/" in links
    assert "/se/p/12345-67890" not in links
    assert "/se/checkout/" not in links


def test_extract_category_links_empty():
    links = _extract_category_links("<html><body>No links</body></html>")
    assert len(links) == 0
