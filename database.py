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
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def upsert_product(conn, product):
    conn.execute("""
        INSERT INTO products (product_id, product_name, category, clothing_type, material_composition, product_url)
        VALUES (:product_id, :product_name, :category, :clothing_type, :material_composition, :product_url)
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = excluded.product_name,
            category = excluded.category,
            clothing_type = excluded.clothing_type,
            material_composition = excluded.material_composition,
            product_url = excluded.product_url,
            scraped_at = CURRENT_TIMESTAMP;
    """, product)
    conn.commit()
