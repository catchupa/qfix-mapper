import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "products.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE NOT NULL,
            product_name TEXT,
            category TEXT,
            clothing_type TEXT,
            material_composition TEXT,
            product_url TEXT,
            description TEXT,
            color TEXT,
            brand TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def migrate_products_table(conn):
    """Add new columns to existing products table if they don't exist."""
    for column in ("description TEXT", "color TEXT", "brand TEXT"):
        try:
            conn.execute(f"ALTER TABLE products ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


def create_table_v2(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gtin TEXT NOT NULL,
            article_number TEXT NOT NULL,
            product_name TEXT,
            description TEXT,
            category TEXT,
            size TEXT,
            color TEXT,
            materials TEXT,
            care_text TEXT,
            brand TEXT,
            country_of_origin TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(gtin)
        );
    """)
    conn.commit()


def upsert_product_v2(conn, product):
    conn.execute("""
        INSERT INTO products_v2 (gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin)
        VALUES (:gtin, :article_number, :product_name, :description, :category, :size, :color, :materials, :care_text, :brand, :country_of_origin)
        ON CONFLICT (gtin) DO UPDATE SET
            article_number = excluded.article_number,
            product_name = excluded.product_name,
            description = excluded.description,
            category = excluded.category,
            size = excluded.size,
            color = excluded.color,
            materials = excluded.materials,
            care_text = excluded.care_text,
            brand = excluded.brand,
            country_of_origin = excluded.country_of_origin,
            uploaded_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


def create_table_ginatricot(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ginatricot_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE NOT NULL,
            product_name TEXT,
            category TEXT,
            clothing_type TEXT,
            material_composition TEXT,
            product_url TEXT,
            description TEXT,
            color TEXT,
            brand TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def upsert_product_ginatricot(conn, product):
    conn.execute("""
        INSERT INTO ginatricot_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url, :description, :color, :brand)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name,
            category = excluded.category,
            clothing_type = excluded.clothing_type,
            material_composition = excluded.material_composition,
            product_url = excluded.product_url,
            description = excluded.description,
            color = excluded.color,
            brand = excluded.brand,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()


def upsert_product(conn, product):
    conn.execute("""
        INSERT INTO products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url, :description, :color, :brand)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name,
            category = excluded.category,
            clothing_type = excluded.clothing_type,
            material_composition = excluded.material_composition,
            product_url = excluded.product_url,
            description = excluded.description,
            color = excluded.color,
            brand = excluded.brand,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()
