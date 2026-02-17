"""Integration tests for API endpoints using Flask test client."""
import io
import json
import sqlite3
from unittest.mock import patch


def _seed_v1_product(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand)
        VALUES ('131367', 'Bootcut jeans', 'dam', 'Jeans > Bootcut', '75% Bomull', 'https://kappahl.com/131367', 'Snygga jeans', 'Svart', 'KappAhl')
    """)
    conn.commit()
    conn.close()


def _seed_gt_product(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO ginatricot_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand)
        VALUES ('225549000', 'Structure maxi skirt', 'klader', 'kjolar > langkjolar', 'Bomull 57%', 'https://ginatricot.com/225549000', 'En fin kjol', 'Black', 'Gina Tricot')
    """)
    conn.commit()
    conn.close()


def _seed_eton_product(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO eton_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand)
        VALUES ('2567-00-10', 'Vit poplinskjorta', 'businesskjortor', 'Businesskjortor > Vita skjortor', '100% Bomull', 'https://www.etonshirts.com/se/sv/product/white-poplin-shirt', 'Ikonisk businesskjorta', 'Vit', 'Eton')
    """)
    conn.commit()
    conn.close()


def _seed_lindex_product(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO lindex_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand)
        VALUES ('3010022', 'Krinklad midi klänning', 'dam', 'Dam > Klänningar', '70% viskos 30% polyamid', 'https://www.lindex.com/se/p/3010022-7258', 'Midiklänning med rynk', 'Light Dusty Pink', 'Lindex')
    """)
    conn.commit()
    conn.close()


def _seed_nudie_product(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO nudie_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand)
        VALUES ('115053', 'Steady Eddie II Sand Storm', 'jeans', 'Men''s Jeans > Regular Tapered', '100% Cotton', 'https://www.nudiejeans.com/en-SE/product/steady-eddie-ii-sand-storm', 'Regular fit jeans', NULL, 'Nudie Jeans')
    """)
    conn.commit()
    conn.close()


def _seed_v2_product(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO products_v2 (gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin)
        VALUES ('7394712345678', '26414', 'Structure maxi skirt', 'English description', 'Knitwear', 'M', 'Black', '[{"name": "Cotton", "percentage": 0.57}]', 'Wash at 40', 'Gina Tricot', 'Bangladesh')
    """)
    conn.commit()
    conn.close()


# ── v1 KappAhl endpoints ─────────────────────────────────────────────────

def test_get_product(app_client):
    client, db_path = app_client
    _seed_v1_product(db_path)

    resp = client.get("/product/131367")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["kappahl"]["product_id"] == "131367"
    assert data["kappahl"]["product_name"] == "Bootcut jeans"
    assert data["kappahl"]["description"] == "Snygga jeans"
    assert data["kappahl"]["color"] == "Svart"
    assert data["kappahl"]["brand"] == "KappAhl"
    assert "qfix" in data


def test_get_product_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/product/999999")
    assert resp.status_code == 404


def test_list_products(app_client):
    client, db_path = app_client
    _seed_v1_product(db_path)

    resp = client.get("/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]["product_id"] == "131367"


# ── v2 protocol endpoints ────────────────────────────────────────────────

def test_v2_get_by_gtin(app_client):
    client, db_path = app_client
    _seed_v2_product(db_path)

    resp = client.get("/v2/product/gtin/7394712345678")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["product"]["gtin"] == "7394712345678"
    assert data["product"]["product_name"] == "Structure maxi skirt"


def test_v2_get_by_gtin_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/v2/product/gtin/0000000000000")
    assert resp.status_code == 404


def test_v2_get_by_article(app_client):
    client, db_path = app_client
    _seed_v2_product(db_path)

    resp = client.get("/v2/product/article/26414")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["article_number"] == "26414"
    assert len(data["variants"]) >= 1


def test_v2_list_products(app_client):
    client, db_path = app_client
    _seed_v2_product(db_path)

    resp = client.get("/v2/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1


# ── v3 Gina Tricot scraper endpoints ─────────────────────────────────────

def test_v3_get_product(app_client):
    client, db_path = app_client
    _seed_gt_product(db_path)

    resp = client.get("/v3/product/225549000")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["product"]["product_id"] == "225549000"
    assert data["product"]["product_name"] == "Structure maxi skirt"
    assert data["product"]["brand"] == "Gina Tricot"
    assert "qfix" in data


def test_v3_get_product_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/v3/product/000000000")
    assert resp.status_code == 404


def test_v3_list_products(app_client):
    client, db_path = app_client
    _seed_gt_product(db_path)

    resp = client.get("/v3/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]["product_name"] == "Structure maxi skirt"


def test_v3_search(app_client):
    client, db_path = app_client
    _seed_gt_product(db_path)

    resp = client.get("/v3/product/search?q=maxi")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert "maxi" in data[0]["product_name"].lower()


def test_v3_search_no_query(app_client):
    client, db_path = app_client
    resp = client.get("/v3/product/search")
    assert resp.status_code == 400


# ── v4 aggregated endpoints ──────────────────────────────────────────────

def test_v4_get_product_merged(app_client):
    """When both scraper and protocol data exist, should merge."""
    client, db_path = app_client
    _seed_gt_product(db_path)
    _seed_v2_product(db_path)  # Same product_name "Structure maxi skirt"

    resp = client.get("/v4/product/225549000")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["product"]["source"] == "merged"
    assert data["product"]["description_sv"] == "En fin kjol"
    assert data["product"]["description_en"] == "English description"
    assert data["product"]["care_text"] == "Wash at 40"
    assert data["product"]["country_of_origin"] == "Bangladesh"
    assert data["product"]["clothing_type"] == "kjolar > langkjolar"


def test_v4_get_product_scraper_only(app_client):
    """When no protocol data exists, should return scraper_only."""
    client, db_path = app_client
    _seed_gt_product(db_path)

    resp = client.get("/v4/product/225549000")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["product"]["source"] == "scraper_only"


def test_v4_get_product_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/v4/product/000000000")
    assert resp.status_code == 404


def test_v4_list_products(app_client):
    client, db_path = app_client
    _seed_gt_product(db_path)

    resp = client.get("/v4/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1


def test_v4_search(app_client):
    client, db_path = app_client
    _seed_gt_product(db_path)

    resp = client.get("/v4/product/search?q=maxi")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1


# ── Eton endpoints ──────────────────────────────────────────────────────

def test_eton_get_product(app_client):
    client, db_path = app_client
    _seed_eton_product(db_path)

    resp = client.get("/eton/product/2567-00-10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["eton"]["product_id"] == "2567-00-10"
    assert data["eton"]["product_name"] == "Vit poplinskjorta"
    assert data["eton"]["brand"] == "Eton"
    assert "qfix" in data


def test_eton_get_product_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/eton/product/0000-00-00")
    assert resp.status_code == 404


def test_eton_list_products(app_client):
    client, db_path = app_client
    _seed_eton_product(db_path)

    resp = client.get("/eton/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]["product_name"] == "Vit poplinskjorta"


# ── Lindex endpoints ────────────────────────────────────────────────────

def test_lindex_get_product(app_client):
    client, db_path = app_client
    _seed_lindex_product(db_path)

    resp = client.get("/lindex/product/3010022")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["lindex"]["product_id"] == "3010022"
    assert data["lindex"]["product_name"] == "Krinklad midi klänning"
    assert data["lindex"]["brand"] == "Lindex"
    assert data["lindex"]["material_composition"] == "70% viskos 30% polyamid"
    assert "qfix" in data


def test_lindex_get_product_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/lindex/product/000000")
    assert resp.status_code == 404


def test_lindex_list_products(app_client):
    client, db_path = app_client
    _seed_lindex_product(db_path)

    resp = client.get("/lindex/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]["product_name"] == "Krinklad midi klänning"


# ── Nudie endpoints ─────────────────────────────────────────────────────

def test_nudie_get_product(app_client):
    client, db_path = app_client
    _seed_nudie_product(db_path)

    resp = client.get("/nudie/product/115053")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["nudie"]["product_id"] == "115053"
    assert data["nudie"]["product_name"] == "Steady Eddie II Sand Storm"
    assert data["nudie"]["brand"] == "Nudie Jeans"
    assert data["nudie"]["material_composition"] == "100% Cotton"
    assert "qfix" in data


def test_nudie_get_product_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/nudie/product/000000")
    assert resp.status_code == 404


def test_nudie_list_products(app_client):
    client, db_path = app_client
    _seed_nudie_product(db_path)

    resp = client.get("/nudie/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]["product_name"] == "Steady Eddie II Sand Storm"


# ── Vision identify endpoint ─────────────────────────────────────────────

@patch("api.classify_and_map")
def test_identify(mock_classify, app_client):
    client, db_path = app_client
    mock_classify.return_value = {
        "classification": {
            "clothing_type": "Trousers",
            "material": "Standard textile",
            "color": "Blue",
            "category": "Women's Clothing",
        },
        "qfix": {
            "qfix_clothing_type": "Trousers",
            "qfix_clothing_type_id": 174,
            "qfix_material": "Standard textile",
            "qfix_material_id": 69,
            "qfix_subcategory": "Women's Clothing",
            "qfix_subcategory_id": 55,
            "qfix_url": "https://kappahl.dev.qfixr.me/sv/?category_id=174&material_id=69",
        },
    }

    data = {"image": (io.BytesIO(b"fake image data"), "test.jpg", "image/jpeg")}
    resp = client.post("/identify", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    result = resp.get_json()
    assert result["classification"]["clothing_type"] == "Trousers"
    assert result["qfix"]["qfix_url"] is not None


def test_identify_no_image(app_client):
    client, db_path = app_client
    resp = client.post("/identify")
    assert resp.status_code == 400
