import os

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE_WRITE_URL = os.environ.get("DATABASE_WRITE_URL")

# All columns in products_unified (excluding id and updated_at)
PRODUCT_COLUMNS = [
    "product_id", "brand", "sub_brand", "product_name", "description", "category",
    "clothing_type", "material_composition", "materials", "color", "size",
    "gtin", "article_number", "product_url", "image_url", "care_text",
    "country_of_origin",
]


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def get_write_connection():
    url = DATABASE_WRITE_URL or DATABASE_URL
    conn = psycopg2.connect(url)
    conn.autocommit = True
    return conn


def create_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products_unified (
                id SERIAL PRIMARY KEY,
                product_id TEXT NOT NULL,
                brand TEXT NOT NULL,
                sub_brand TEXT,
                product_name TEXT,
                description TEXT,
                category TEXT,
                clothing_type TEXT,
                material_composition TEXT,
                materials TEXT,
                color TEXT,
                size TEXT,
                gtin TEXT,
                article_number TEXT,
                product_url TEXT,
                image_url TEXT,
                care_text TEXT,
                country_of_origin TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (brand, product_id)
            );
        """)
        # QFix mapping columns (persisted by /remap/run, not by scrapers)
        for col, col_type in [
            ("qfix_clothing_type", "TEXT"),
            ("qfix_clothing_type_id", "INTEGER"),
            ("qfix_material", "TEXT"),
            ("qfix_material_id", "INTEGER"),
            ("qfix_url", "TEXT"),
        ]:
            cur.execute(f"ALTER TABLE products_unified ADD COLUMN IF NOT EXISTS {col} {col_type};")


def upsert_product(conn, product):
    """Upsert a product into products_unified.

    product must be a dict with at least 'brand' and 'product_id'.
    All other fields are optional and will be set to NULL if missing.
    """
    # Build the dict with defaults for missing keys
    values = {col: product.get(col) for col in PRODUCT_COLUMNS}

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO products_unified (product_id, brand, sub_brand, product_name, description, category,
                clothing_type, material_composition, materials, color, size,
                gtin, article_number, product_url, image_url, care_text, country_of_origin)
            VALUES (%(product_id)s, %(brand)s, %(sub_brand)s, %(product_name)s, %(description)s, %(category)s,
                %(clothing_type)s, %(material_composition)s, %(materials)s, %(color)s, %(size)s,
                %(gtin)s, %(article_number)s, %(product_url)s, %(image_url)s, %(care_text)s, %(country_of_origin)s)
            ON CONFLICT (brand, product_id) DO UPDATE SET
                sub_brand = EXCLUDED.sub_brand,
                product_name = EXCLUDED.product_name,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                clothing_type = EXCLUDED.clothing_type,
                material_composition = EXCLUDED.material_composition,
                materials = EXCLUDED.materials,
                color = EXCLUDED.color,
                size = EXCLUDED.size,
                gtin = EXCLUDED.gtin,
                article_number = EXCLUDED.article_number,
                product_url = EXCLUDED.product_url,
                image_url = EXCLUDED.image_url,
                care_text = EXCLUDED.care_text,
                country_of_origin = EXCLUDED.country_of_origin,
                updated_at = CURRENT_TIMESTAMP;
        """, values)


def update_qfix_mapping(conn, brand, product_id, qfix_data):
    """Update only the 5 QFix mapping columns for a given product.

    qfix_data should be a dict with keys:
      qfix_clothing_type, qfix_clothing_type_id, qfix_material,
      qfix_material_id, qfix_url
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE products_unified
            SET qfix_clothing_type = %(qfix_clothing_type)s,
                qfix_clothing_type_id = %(qfix_clothing_type_id)s,
                qfix_material = %(qfix_material)s,
                qfix_material_id = %(qfix_material_id)s,
                qfix_url = %(qfix_url)s
            WHERE brand = %(brand)s AND product_id = %(product_id)s
        """, {
            "brand": brand,
            "product_id": product_id,
            "qfix_clothing_type": qfix_data.get("qfix_clothing_type"),
            "qfix_clothing_type_id": qfix_data.get("qfix_clothing_type_id"),
            "qfix_material": qfix_data.get("qfix_material"),
            "qfix_material_id": qfix_data.get("qfix_material_id"),
            "qfix_url": qfix_data.get("qfix_url"),
        })
