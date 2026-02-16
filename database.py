import os

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def create_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                product_id TEXT UNIQUE NOT NULL,
                product_name TEXT,
                category TEXT,
                clothing_type TEXT,
                material_composition TEXT,
                product_url TEXT,
                description TEXT,
                color TEXT,
                brand TEXT,
                image_url TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


def create_table_v2(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products_v2 (
                id SERIAL PRIMARY KEY,
                gtin TEXT NOT NULL UNIQUE,
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
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


def create_table_ginatricot(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ginatricot_products (
                id SERIAL PRIMARY KEY,
                product_id TEXT UNIQUE NOT NULL,
                product_name TEXT,
                category TEXT,
                clothing_type TEXT,
                material_composition TEXT,
                product_url TEXT,
                description TEXT,
                color TEXT,
                brand TEXT,
                image_url TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


def upsert_product(conn, product):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url)
            VALUES (%(product_id)s, %(product_name)s, %(category)s, %(clothing_type)s, %(material_composition)s, %(product_url)s, %(description)s, %(color)s, %(brand)s, %(image_url)s)
            ON CONFLICT (product_id) DO UPDATE SET
                product_name = EXCLUDED.product_name,
                category = EXCLUDED.category,
                clothing_type = EXCLUDED.clothing_type,
                material_composition = EXCLUDED.material_composition,
                product_url = EXCLUDED.product_url,
                description = EXCLUDED.description,
                color = EXCLUDED.color,
                brand = EXCLUDED.brand,
                image_url = EXCLUDED.image_url,
                scraped_at = CURRENT_TIMESTAMP;
        """, product)


def upsert_product_v2(conn, product):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO products_v2 (gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin)
            VALUES (%(gtin)s, %(article_number)s, %(product_name)s, %(description)s, %(category)s, %(size)s, %(color)s, %(materials)s, %(care_text)s, %(brand)s, %(country_of_origin)s)
            ON CONFLICT (gtin) DO UPDATE SET
                article_number = EXCLUDED.article_number,
                product_name = EXCLUDED.product_name,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                size = EXCLUDED.size,
                color = EXCLUDED.color,
                materials = EXCLUDED.materials,
                care_text = EXCLUDED.care_text,
                brand = EXCLUDED.brand,
                country_of_origin = EXCLUDED.country_of_origin,
                uploaded_at = CURRENT_TIMESTAMP;
        """, product)


def upsert_product_ginatricot(conn, product):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ginatricot_products (product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url)
            VALUES (%(product_id)s, %(product_name)s, %(category)s, %(clothing_type)s, %(material_composition)s, %(product_url)s, %(description)s, %(color)s, %(brand)s, %(image_url)s)
            ON CONFLICT (product_id) DO UPDATE SET
                product_name = EXCLUDED.product_name,
                category = EXCLUDED.category,
                clothing_type = EXCLUDED.clothing_type,
                material_composition = EXCLUDED.material_composition,
                product_url = EXCLUDED.product_url,
                description = EXCLUDED.description,
                color = EXCLUDED.color,
                brand = EXCLUDED.brand,
                image_url = EXCLUDED.image_url,
                scraped_at = CURRENT_TIMESTAMP;
        """, product)
