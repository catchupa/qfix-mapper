"""Tests for database unified table schema and upsert logic (using SQLite for testing)."""
import sqlite3

import pytest


def _make_product(brand="KappAhl", **overrides):
    """Factory for product dicts. Defaults to KappAhl scraper-style product."""
    base = {
        "product_id": "131367",
        "brand": brand,
        "product_name": "Bootcut jeans",
        "category": "dam",
        "clothing_type": "Jeans > Bootcut",
        "material_composition": "75% Bomull, 21% Polyester",
        "product_url": "https://www.kappahl.com/sv-se/dam/jeans/131367",
        "description": "Snygga jeans",
        "color": "Svart",
        "image_url": "https://static.kappahl.com/productimages/131367_f_4.jpg",
    }
    base.update(overrides)
    return base


def _upsert_product(conn, product):
    """SQLite version of the unified upsert."""
    # Ensure all columns have a value (default to None)
    cols = [
        "product_id", "brand", "product_name", "description", "category",
        "clothing_type", "material_composition", "materials", "color", "size",
        "gtin", "article_number", "product_url", "image_url", "care_text",
        "country_of_origin",
    ]
    values = {col: product.get(col) for col in cols}

    conn.execute("""
        INSERT INTO products_unified (product_id, brand, product_name, description, category,
            clothing_type, material_composition, materials, color, size,
            gtin, article_number, product_url, image_url, care_text, country_of_origin)
        VALUES (:product_id, :brand, :product_name, :description, :category,
            :clothing_type, :material_composition, :materials, :color, :size,
            :gtin, :article_number, :product_url, :image_url, :care_text, :country_of_origin)
        ON CONFLICT (brand, product_id) DO UPDATE SET
            product_name = excluded.product_name, description = excluded.description,
            category = excluded.category, clothing_type = excluded.clothing_type,
            material_composition = excluded.material_composition, materials = excluded.materials,
            color = excluded.color, size = excluded.size,
            gtin = excluded.gtin, article_number = excluded.article_number,
            product_url = excluded.product_url, image_url = excluded.image_url,
            care_text = excluded.care_text, country_of_origin = excluded.country_of_origin,
            updated_at = CURRENT_TIMESTAMP;
    """, values)
    conn.commit()


# ── Table creation ────────────────────────────────────────────────────────

def test_create_table(db_conn):
    tables = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r[0] for r in tables}
    assert "products_unified" in names


def test_create_table_idempotent(db_conn):
    """Creating tables again should not raise."""
    from tests.conftest import _create_tables_sqlite
    _create_tables_sqlite(db_conn)


# ── Upsert products (various brands) ─────────────────────────────────────

def test_upsert_product_insert(db_conn):
    product = _make_product()
    _upsert_product(db_conn, product)

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'KappAhl' AND product_id = '131367'"
    ).fetchone()
    assert row is not None
    assert row["product_name"] == "Bootcut jeans"
    assert row["description"] == "Snygga jeans"
    assert row["color"] == "Svart"
    assert row["brand"] == "KappAhl"


def test_upsert_product_update(db_conn):
    _upsert_product(db_conn, _make_product())
    _upsert_product(db_conn, _make_product(product_name="Updated jeans", color="Blå"))

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'KappAhl' AND product_id = '131367'"
    ).fetchone()
    assert row["product_name"] == "Updated jeans"
    assert row["color"] == "Blå"


def test_upsert_ginatricot(db_conn):
    product = _make_product(
        brand="Gina Tricot", product_id="225549000",
        product_name="Structure maxi skirt", category="klader",
        clothing_type="kjolar > langkjolar", material_composition="Bomull 57%",
    )
    _upsert_product(db_conn, product)

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Gina Tricot' AND product_id = '225549000'"
    ).fetchone()
    assert row is not None
    assert row["product_name"] == "Structure maxi skirt"
    assert row["brand"] == "Gina Tricot"


def test_upsert_eton(db_conn):
    product = _make_product(
        brand="Eton", product_id="2567-00-10",
        product_name="Vit poplinskjorta", material_composition="100% Bomull",
    )
    _upsert_product(db_conn, product)

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Eton' AND product_id = '2567-00-10'"
    ).fetchone()
    assert row is not None
    assert row["product_name"] == "Vit poplinskjorta"
    assert row["brand"] == "Eton"
    assert row["material_composition"] == "100% Bomull"


def test_upsert_eton_update(db_conn):
    product = _make_product(brand="Eton", product_id="2567-00-10", color="Vit")
    _upsert_product(db_conn, product)
    _upsert_product(db_conn, _make_product(brand="Eton", product_id="2567-00-10", color="Blå"))

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Eton' AND product_id = '2567-00-10'"
    ).fetchone()
    assert row["color"] == "Blå"


def test_upsert_nudie(db_conn):
    product = _make_product(
        brand="Nudie Jeans", product_id="115053",
        product_name="Steady Eddie II Sand Storm",
        material_composition="100% Cotton", color=None,
    )
    _upsert_product(db_conn, product)

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Nudie Jeans' AND product_id = '115053'"
    ).fetchone()
    assert row is not None
    assert row["product_name"] == "Steady Eddie II Sand Storm"
    assert row["material_composition"] == "100% Cotton"


def test_upsert_nudie_update(db_conn):
    product = _make_product(brand="Nudie Jeans", product_id="115053")
    _upsert_product(db_conn, product)
    _upsert_product(db_conn, _make_product(
        brand="Nudie Jeans", product_id="115053",
        material_composition="98% Cotton 2% Elastane",
    ))

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Nudie Jeans' AND product_id = '115053'"
    ).fetchone()
    assert row["material_composition"] == "98% Cotton 2% Elastane"


def test_upsert_lindex(db_conn):
    product = _make_product(
        brand="Lindex", product_id="3010022",
        product_name="Krinklad midi klänning",
        material_composition="70% viskos 30% polyamid",
    )
    _upsert_product(db_conn, product)

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Lindex' AND product_id = '3010022'"
    ).fetchone()
    assert row is not None
    assert row["product_name"] == "Krinklad midi klänning"
    assert row["material_composition"] == "70% viskos 30% polyamid"


def test_upsert_lindex_update(db_conn):
    product = _make_product(brand="Lindex", product_id="3010022")
    _upsert_product(db_conn, product)
    _upsert_product(db_conn, _make_product(brand="Lindex", product_id="3010022", color="Dark Blue"))

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Lindex' AND product_id = '3010022'"
    ).fetchone()
    assert row["color"] == "Dark Blue"


# ── Protocol (v2) style products ──────────────────────────────────────────

def test_upsert_v2_product(db_conn):
    product = _make_product(
        brand="Gina Tricot", product_id="v2-7394712345678",
        product_name="Front seam flare jeans",
        description="Flare jeans with high waist",
        category="Denim",
        gtin="7394712345678", article_number="26414", size="M",
        materials='[{"name": "Cotton", "percentage": 0.98}]',
        care_text="Wash at 40", country_of_origin="Bangladesh",
    )
    _upsert_product(db_conn, product)

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Gina Tricot' AND product_id = 'v2-7394712345678'"
    ).fetchone()
    assert row is not None
    assert row["product_name"] == "Front seam flare jeans"
    assert row["gtin"] == "7394712345678"
    assert row["country_of_origin"] == "Bangladesh"


def test_upsert_v2_product_update(db_conn):
    product = _make_product(
        brand="Gina Tricot", product_id="v2-7394712345678",
        gtin="7394712345678", article_number="26414",
    )
    _upsert_product(db_conn, product)
    _upsert_product(db_conn, _make_product(
        brand="Gina Tricot", product_id="v2-7394712345678",
        product_name="Updated jeans", gtin="7394712345678", article_number="26414",
    ))

    row = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'Gina Tricot' AND product_id = 'v2-7394712345678'"
    ).fetchone()
    assert row["product_name"] == "Updated jeans"


# ── Unique constraint ─────────────────────────────────────────────────────

def test_same_product_id_different_brands(db_conn):
    """Same product_id with different brands should create separate rows."""
    _upsert_product(db_conn, _make_product(brand="KappAhl", product_id="12345", product_name="KappAhl product"))
    _upsert_product(db_conn, _make_product(brand="Eton", product_id="12345", product_name="Eton product"))

    rows = db_conn.execute(
        "SELECT * FROM products_unified WHERE product_id = '12345' ORDER BY brand"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["brand"] == "Eton"
    assert rows[0]["product_name"] == "Eton product"
    assert rows[1]["brand"] == "KappAhl"
    assert rows[1]["product_name"] == "KappAhl product"


def test_unique_constraint_same_brand_product_id(db_conn):
    """Inserting same (brand, product_id) should upsert, not duplicate."""
    _upsert_product(db_conn, _make_product(brand="KappAhl", product_id="12345", product_name="First"))
    _upsert_product(db_conn, _make_product(brand="KappAhl", product_id="12345", product_name="Second"))

    rows = db_conn.execute(
        "SELECT * FROM products_unified WHERE brand = 'KappAhl' AND product_id = '12345'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["product_name"] == "Second"
