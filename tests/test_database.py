"""Tests for database operations."""
import sqlite3

from database import (
    create_table,
    create_table_v2,
    create_table_ginatricot,
    upsert_product,
    upsert_product_v2,
    upsert_product_ginatricot,
    migrate_products_table,
)


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


def test_create_table_idempotent(db_conn):
    """Calling create_table again should not raise."""
    create_table(db_conn)
    create_table_v2(db_conn)
    create_table_ginatricot(db_conn)


# ── Migration ─────────────────────────────────────────────────────────────

def test_migrate_products_table():
    """Migration should add columns and be idempotent."""
    conn = sqlite3.connect(":memory:")
    # Create table WITHOUT new columns (old schema)
    conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE NOT NULL,
            product_name TEXT,
            category TEXT,
            clothing_type TEXT,
            material_composition TEXT,
            product_url TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    migrate_products_table(conn)

    # Verify columns exist by inserting a full row
    conn.execute(
        "INSERT INTO products (product_id, description, color, brand) VALUES ('1', 'desc', 'red', 'brand')"
    )
    row = conn.execute("SELECT description, color, brand FROM products WHERE product_id = '1'").fetchone()
    assert row[0] == "desc"
    assert row[1] == "red"
    assert row[2] == "brand"

    # Running again should not raise
    migrate_products_table(conn)
    conn.close()


# ── Upsert v1 products ───────────────────────────────────────────────────

def test_upsert_product_insert(db_conn):
    product = _make_v1_product()
    upsert_product(db_conn, product)

    row = db_conn.execute("SELECT * FROM products WHERE product_id = '131367'").fetchone()
    assert row is not None
    assert row["product_name"] == "Bootcut jeans"
    assert row["description"] == "Snygga jeans"
    assert row["color"] == "Svart"
    assert row["brand"] == "KappAhl"


def test_upsert_product_update(db_conn):
    upsert_product(db_conn, _make_v1_product())
    upsert_product(db_conn, _make_v1_product(product_name="Updated jeans", color="Blå"))

    row = db_conn.execute("SELECT * FROM products WHERE product_id = '131367'").fetchone()
    assert row["product_name"] == "Updated jeans"
    assert row["color"] == "Blå"


# ── Upsert Gina Tricot products ──────────────────────────────────────────

def test_upsert_product_ginatricot_insert(db_conn):
    upsert_product_ginatricot(db_conn, _make_gt_product())

    row = db_conn.execute("SELECT * FROM ginatricot_products WHERE product_id = '225549000'").fetchone()
    assert row is not None
    assert row["product_name"] == "Structure maxi skirt"
    assert row["brand"] == "Gina Tricot"


def test_upsert_product_ginatricot_update(db_conn):
    upsert_product_ginatricot(db_conn, _make_gt_product())
    upsert_product_ginatricot(db_conn, _make_gt_product(color="White"))

    row = db_conn.execute("SELECT * FROM ginatricot_products WHERE product_id = '225549000'").fetchone()
    assert row["color"] == "White"


# ── Upsert v2 products ───────────────────────────────────────────────────

def test_upsert_product_v2_insert(db_conn):
    upsert_product_v2(db_conn, _make_v2_product())

    row = db_conn.execute("SELECT * FROM products_v2 WHERE gtin = '7394712345678'").fetchone()
    assert row is not None
    assert row["product_name"] == "Front seam flare jeans"
    assert row["country_of_origin"] == "Bangladesh"


def test_upsert_product_v2_update(db_conn):
    upsert_product_v2(db_conn, _make_v2_product())
    upsert_product_v2(db_conn, _make_v2_product(product_name="Updated jeans"))

    row = db_conn.execute("SELECT * FROM products_v2 WHERE gtin = '7394712345678'").fetchone()
    assert row["product_name"] == "Updated jeans"
