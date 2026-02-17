"""Integration tests for API endpoints using Flask test client."""
import io
import json
import sqlite3
from unittest.mock import patch


def _seed_product(db_path, product_id, brand, product_name, category, clothing_type,
                  material_composition, product_url, description, color,
                  gtin=None, article_number=None, size=None, materials=None,
                  care_text=None, country_of_origin=None, image_url=None):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO products_unified (product_id, brand, product_name, category, clothing_type,
            material_composition, product_url, description, color, gtin, article_number, size,
            materials, care_text, country_of_origin, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_id, brand, product_name, category, clothing_type,
          material_composition, product_url, description, color, gtin, article_number, size,
          materials, care_text, country_of_origin, image_url))
    conn.commit()
    conn.close()


def _seed_kappahl_product(db_path):
    _seed_product(db_path,
        product_id='131367', brand='KappAhl', product_name='Bootcut jeans',
        category='dam', clothing_type='Jeans > Bootcut',
        material_composition='75% Bomull', product_url='https://kappahl.com/131367',
        description='Snygga jeans', color='Svart')


def _seed_gt_product(db_path):
    _seed_product(db_path,
        product_id='225549000', brand='Gina Tricot', product_name='Structure maxi skirt',
        category='klader', clothing_type='kjolar > langkjolar',
        material_composition='Bomull 57%', product_url='https://ginatricot.com/225549000',
        description='En fin kjol', color='Black')


def _seed_eton_product(db_path):
    _seed_product(db_path,
        product_id='2567-00-10', brand='Eton', product_name='Vit poplinskjorta',
        category='businesskjortor', clothing_type='Businesskjortor > Vita skjortor',
        material_composition='100% Bomull', product_url='https://www.etonshirts.com/se/sv/product/white-poplin-shirt',
        description='Ikonisk businesskjorta', color='Vit')


def _seed_lindex_product(db_path):
    _seed_product(db_path,
        product_id='3010022', brand='Lindex', product_name='Krinklad midi klänning',
        category='dam', clothing_type='Dam > Klänningar',
        material_composition='70% viskos 30% polyamid', product_url='https://www.lindex.com/se/p/3010022-7258',
        description='Midiklänning med rynk', color='Light Dusty Pink')


def _seed_nudie_product(db_path):
    _seed_product(db_path,
        product_id='115053', brand='Nudie Jeans', product_name='Steady Eddie II Sand Storm',
        category='jeans', clothing_type="Men's Jeans > Regular Tapered",
        material_composition='100% Cotton', product_url='https://www.nudiejeans.com/en-SE/product/steady-eddie-ii-sand-storm',
        description='Regular fit jeans', color=None)


def _seed_v2_product(db_path):
    _seed_product(db_path,
        product_id='v2-7394712345678', brand='Gina Tricot', product_name='Structure maxi skirt',
        category='Knitwear', clothing_type=None,
        material_composition=None, product_url=None,
        description='English description', color='Black',
        gtin='7394712345678', article_number='26414', size='M',
        materials='[{"name": "Cotton", "percentage": 0.57}]',
        care_text='Wash at 40', country_of_origin='Bangladesh')


def _seed_gt_product_with_protocol(db_path):
    """Seed a Gina Tricot product that has both scraped and protocol data in one row."""
    _seed_product(db_path,
        product_id='225549000', brand='Gina Tricot', product_name='Structure maxi skirt',
        category='klader', clothing_type='kjolar > langkjolar',
        material_composition='Bomull 57%', product_url='https://ginatricot.com/225549000',
        description='En fin kjol', color='Black',
        article_number='26414', care_text='Wash at 40', country_of_origin='Bangladesh',
        materials='[{"name": "Cotton", "percentage": 0.57}]')


# ── v1 KappAhl endpoints ─────────────────────────────────────────────────

def test_get_product(app_client):
    client, db_path = app_client
    _seed_kappahl_product(db_path)

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
    _seed_kappahl_product(db_path)

    resp = client.get("/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]["product_id"] == "131367"


def test_kappahl_get_product(app_client):
    client, db_path = app_client
    _seed_kappahl_product(db_path)

    resp = client.get("/kappahl/product/131367")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["kappahl"]["product_id"] == "131367"
    assert data["kappahl"]["brand"] == "KappAhl"
    assert "qfix" in data


def test_kappahl_get_product_not_found(app_client):
    client, db_path = app_client
    resp = client.get("/kappahl/product/999999")
    assert resp.status_code == 404


def test_kappahl_list_products(app_client):
    client, db_path = app_client
    _seed_kappahl_product(db_path)

    resp = client.get("/kappahl/products")
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
    """When product has protocol data (article_number), should show merged."""
    client, db_path = app_client
    _seed_gt_product_with_protocol(db_path)

    resp = client.get("/v4/product/225549000")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["product"]["source"] == "merged"
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
