"""Tests for database table schemas and upsert logic (using SQLite for testing)."""
import sqlite3


def _make_v1_product(**overrides):
    base = {
        "product_id": "131367",
        "product_name": "Bootcut jeans",
        "category": "dam",
        "clothing_type": "Jeans > Bootcut",
        "material_composition": "75% Bomull, 21% Polyester",
        "product_url": "https://www.kappahl.com/sv-se/dam/jeans/131367",
        "description": "Snygga jeans",
        "color": "Svart",
        "brand": "KappAhl",
        "image_url": "https://static.kappahl.com/productimages/131367_f_4.jpg",
    }
    base.update(overrides)
    return base


def _make_gt_product(**overrides):
    base = {
        "product_id": "225549000",
        "product_name": "Structure maxi skirt",
        "category": "klader",
        "clothing_type": "kjolar > langkjolar",
        "material_composition": "Bomull 57%",
        "product_url": "https://www.ginatricot.com/se/klader/kjolar/langkjolar/structure-maxi-skirt-225549000",
        "description": "En fin kjol",
        "color": "Black",
        "brand": "Gina Tricot",
        "image_url": "https://ginatricot-pim.imgix.net/225549000/22554900001.jpg",
    }
    base.update(overrides)
    return base


def _make_eton_product(**overrides):
    base = {
        "product_id": "2567-00-10",
        "product_name": "Vit poplinskjorta",
        "category": "businesskjortor",
        "clothing_type": "Businesskjortor > Vita skjortor",
        "material_composition": "100% Bomull",
        "product_url": "https://www.etonshirts.com/se/sv/product/white-poplin-shirt",
        "description": "Ikonisk businesskjorta i bomullspoplin",
        "color": "Vit",
        "brand": "Eton",
        "image_url": "https://api.etonshirts.com/v1/retail/image/1080/white-poplin-shirt.webp",
    }
    base.update(overrides)
    return base


def _make_nudie_product(**overrides):
    base = {
        "product_id": "115053",
        "product_name": "Steady Eddie II Sand Storm",
        "category": "men's jeans",
        "clothing_type": "Men's Jeans > Regular Tapered",
        "material_composition": "100% Cotton",
        "product_url": "https://www.nudiejeans.com/en-SE/product/steady-eddie-ii-sand-storm",
        "description": "Regular fit jeans with a tapered leg",
        "color": None,
        "brand": "Nudie Jeans",
        "image_url": "https://nudie.centracdn.net/client/dynamic/images/115053.jpg",
    }
    base.update(overrides)
    return base


def _make_lindex_product(**overrides):
    base = {
        "product_id": "3010022",
        "product_name": "Krinklad midi klänning",
        "category": "dam",
        "clothing_type": "Dam > Klänningar",
        "material_composition": "70% viskos 30% polyamid",
        "product_url": "https://www.lindex.com/se/p/3010022-7258",
        "description": "Midiklänning med rynk, v-ringning och en böljande passform.",
        "color": "Light Dusty Pink",
        "brand": "Lindex",
        "image_url": "https://i8.amplience.net/s/Lindex/3010022_7258_ProductVariant",
    }
    base.update(overrides)
    return base


def _make_v2_product(**overrides):
    base = {
        "gtin": "7394712345678",
        "article_number": "26414",
        "product_name": "Front seam flare jeans",
        "description": "Flare jeans with high waist",
        "category": "Denim",
        "size": "M",
        "color": "Black",
        "materials": '[{"name": "Cotton", "percentage": 0.98}]',
        "care_text": "Wash at 40",
        "brand": "Gina Tricot",
        "country_of_origin": "Bangladesh",
    }
    base.update(overrides)
    return base


def _upsert_product(conn, product):
    conn.execute("""
        INSERT INTO products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url, :description, :color, :brand, :image_url)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name, category = excluded.category,
            clothing_type = excluded.clothing_type, material_composition = excluded.material_composition,
            product_url = excluded.product_url, description = excluded.description,
            color = excluded.color, brand = excluded.brand, image_url = excluded.image_url,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


def _upsert_product_v2(conn, product):
    conn.execute("""
        INSERT INTO products_v2 (gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin)
        VALUES (:gtin, :article_number, :product_name, :description, :category, :size, :color, :materials, :care_text, :brand, :country_of_origin)
        ON CONFLICT (gtin) DO UPDATE SET
            article_number = excluded.article_number, product_name = excluded.product_name,
            description = excluded.description, category = excluded.category,
            size = excluded.size, color = excluded.color, materials = excluded.materials,
            care_text = excluded.care_text, brand = excluded.brand,
            country_of_origin = excluded.country_of_origin, uploaded_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


def _upsert_product_eton(conn, product):
    conn.execute("""
        INSERT INTO eton_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url, :description, :color, :brand, :image_url)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name, category = excluded.category,
            clothing_type = excluded.clothing_type, material_composition = excluded.material_composition,
            product_url = excluded.product_url, description = excluded.description,
            color = excluded.color, brand = excluded.brand, image_url = excluded.image_url,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


def _upsert_product_lindex(conn, product):
    conn.execute("""
        INSERT INTO lindex_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url, :description, :color, :brand, :image_url)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name, category = excluded.category,
            clothing_type = excluded.clothing_type, material_composition = excluded.material_composition,
            product_url = excluded.product_url, description = excluded.description,
            color = excluded.color, brand = excluded.brand, image_url = excluded.image_url,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


def _upsert_product_nudie(conn, product):
    conn.execute("""
        INSERT INTO nudie_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url, :description, :color, :brand, :image_url)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name, category = excluded.category,
            clothing_type = excluded.clothing_type, material_composition = excluded.material_composition,
            product_url = excluded.product_url, description = excluded.description,
            color = excluded.color, brand = excluded.brand, image_url = excluded.image_url,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


def _upsert_product_ginatricot(conn, product):
    conn.execute("""
        INSERT INTO ginatricot_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url, :description, :color, :brand, :image_url)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name, category = excluded.category,
            clothing_type = excluded.clothing_type, material_composition = excluded.material_composition,
            product_url = excluded.product_url, description = excluded.description,
            color = excluded.color, brand = excluded.brand, image_url = excluded.image_url,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


# ── Table creation ────────────────────────────────────────────────────────

def test_create_table(db_conn):
    # Tables already created by fixture; verify they exist
    tables = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r[0] for r in tables}
    assert "products" in names
    assert "products_v2" in names
    assert "ginatricot_products" in names
    assert "eton_products" in names
    assert "nudie_products" in names
    assert "lindex_products" in names


def test_create_table_idempotent(db_conn):
    """Creating tables again should not raise."""
    from tests.conftest import _create_tables_sqlite
    _create_tables_sqlite(db_conn)


# ── Upsert v1 products ───────────────────────────────────────────────────

def test_upsert_product_insert(db_conn):
    product = _make_v1_product()
    _upsert_product(db_conn, product)

    row = db_conn.execute("SELECT * FROM products WHERE product_id = '131367'").fetchone()
    assert row is not None
    assert row["product_name"] == "Bootcut jeans"
    assert row["description"] == "Snygga jeans"
    assert row["color"] == "Svart"
    assert row["brand"] == "KappAhl"


def test_upsert_product_update(db_conn):
    _upsert_product(db_conn, _make_v1_product())
    _upsert_product(db_conn, _make_v1_product(product_name="Updated jeans", color="Blå"))

    row = db_conn.execute("SELECT * FROM products WHERE product_id = '131367'").fetchone()
    assert row["product_name"] == "Updated jeans"
    assert row["color"] == "Blå"


# ── Upsert Gina Tricot products ──────────────────────────────────────────

def test_upsert_product_ginatricot_insert(db_conn):
    _upsert_product_ginatricot(db_conn, _make_gt_product())

    row = db_conn.execute("SELECT * FROM ginatricot_products WHERE product_id = '225549000'").fetchone()
    assert row is not None
    assert row["product_name"] == "Structure maxi skirt"
    assert row["brand"] == "Gina Tricot"


def test_upsert_product_ginatricot_update(db_conn):
    _upsert_product_ginatricot(db_conn, _make_gt_product())
    _upsert_product_ginatricot(db_conn, _make_gt_product(color="White"))

    row = db_conn.execute("SELECT * FROM ginatricot_products WHERE product_id = '225549000'").fetchone()
    assert row["color"] == "White"


# ── Upsert Eton products ─────────────────────────────────────────────────

def test_upsert_product_eton_insert(db_conn):
    _upsert_product_eton(db_conn, _make_eton_product())

    row = db_conn.execute("SELECT * FROM eton_products WHERE product_id = '2567-00-10'").fetchone()
    assert row is not None
    assert row["product_name"] == "Vit poplinskjorta"
    assert row["brand"] == "Eton"
    assert row["material_composition"] == "100% Bomull"


def test_upsert_product_eton_update(db_conn):
    _upsert_product_eton(db_conn, _make_eton_product())
    _upsert_product_eton(db_conn, _make_eton_product(color="Blå"))

    row = db_conn.execute("SELECT * FROM eton_products WHERE product_id = '2567-00-10'").fetchone()
    assert row["color"] == "Blå"


# ── Upsert Lindex products ───────────────────────────────────────────────

def test_upsert_product_lindex_insert(db_conn):
    _upsert_product_lindex(db_conn, _make_lindex_product())

    row = db_conn.execute("SELECT * FROM lindex_products WHERE product_id = '3010022'").fetchone()
    assert row is not None
    assert row["product_name"] == "Krinklad midi klänning"
    assert row["brand"] == "Lindex"
    assert row["material_composition"] == "70% viskos 30% polyamid"


def test_upsert_product_lindex_update(db_conn):
    _upsert_product_lindex(db_conn, _make_lindex_product())
    _upsert_product_lindex(db_conn, _make_lindex_product(color="Dark Blue"))

    row = db_conn.execute("SELECT * FROM lindex_products WHERE product_id = '3010022'").fetchone()
    assert row["color"] == "Dark Blue"


# ── Upsert Nudie products ────────────────────────────────────────────────

def test_upsert_product_nudie_insert(db_conn):
    _upsert_product_nudie(db_conn, _make_nudie_product())

    row = db_conn.execute("SELECT * FROM nudie_products WHERE product_id = '115053'").fetchone()
    assert row is not None
    assert row["product_name"] == "Steady Eddie II Sand Storm"
    assert row["brand"] == "Nudie Jeans"
    assert row["material_composition"] == "100% Cotton"


def test_upsert_product_nudie_update(db_conn):
    _upsert_product_nudie(db_conn, _make_nudie_product())
    _upsert_product_nudie(db_conn, _make_nudie_product(material_composition="98% Cotton 2% Elastane"))

    row = db_conn.execute("SELECT * FROM nudie_products WHERE product_id = '115053'").fetchone()
    assert row["material_composition"] == "98% Cotton 2% Elastane"


# ── Upsert v2 products ───────────────────────────────────────────────────

def test_upsert_product_v2_insert(db_conn):
    _upsert_product_v2(db_conn, _make_v2_product())

    row = db_conn.execute("SELECT * FROM products_v2 WHERE gtin = '7394712345678'").fetchone()
    assert row is not None
    assert row["product_name"] == "Front seam flare jeans"
    assert row["country_of_origin"] == "Bangladesh"


def test_upsert_product_v2_update(db_conn):
    _upsert_product_v2(db_conn, _make_v2_product())
    _upsert_product_v2(db_conn, _make_v2_product(product_name="Updated jeans"))

    row = db_conn.execute("SELECT * FROM products_v2 WHERE gtin = '7394712345678'").fetchone()
    assert row["product_name"] == "Updated jeans"
