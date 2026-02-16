"""Integration tests for API endpoints using Flask test client."""
import json
import sqlite3


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
