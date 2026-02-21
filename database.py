import json
import logging
import os
import threading
import time

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE_WRITE_URL = os.environ.get("DATABASE_WRITE_URL")

# All columns in products_unified (excluding id and updated_at)
PRODUCT_COLUMNS = [
    "product_id", "brand", "sub_brand", "product_name", "description", "category",
    "clothing_type", "material_composition", "materials", "color", "size",
    "gtin", "article_number", "product_url", "image_url", "care_text",
    "country_of_origin",
]


def _connect_with_retry(dsn, retries=3, delay=1.0):
    """Connect to DB with retry logic and connection timeout."""
    last_err = None
    for attempt in range(retries):
        try:
            conn = psycopg2.connect(dsn, connect_timeout=10)
            conn.autocommit = True
            return conn
        except Exception as e:
            last_err = e
            logger.warning("DB connection attempt %d/%d failed: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise last_err


def get_connection():
    return _connect_with_retry(DATABASE_URL)


def get_write_connection():
    url = DATABASE_WRITE_URL or DATABASE_URL
    return _connect_with_retry(url)


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
                last_seen_in_sitemap TIMESTAMP,
                UNIQUE (brand, product_id)
            );
        """)
        cur.execute("ALTER TABLE products_unified ADD COLUMN IF NOT EXISTS last_seen_in_sitemap TIMESTAMP;")
        # QFix mapping columns (persisted by /remap/run, not by scrapers)
        for col, col_type in [
            ("qfix_clothing_type", "TEXT"),
            ("qfix_clothing_type_id", "INTEGER"),
            ("qfix_material", "TEXT"),
            ("qfix_material_id", "INTEGER"),
            ("qfix_url", "TEXT"),
            ("qfix_url_repair", "TEXT"),
            ("qfix_url_adjustment", "TEXT"),
            ("qfix_url_care", "TEXT"),
            ("qfix_url_other", "TEXT"),
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
                gtin, article_number, product_url, image_url, care_text, country_of_origin,
                last_seen_in_sitemap)
            VALUES (%(product_id)s, %(brand)s, %(sub_brand)s, %(product_name)s, %(description)s, %(category)s,
                %(clothing_type)s, %(material_composition)s, %(materials)s, %(color)s, %(size)s,
                %(gtin)s, %(article_number)s, %(product_url)s, %(image_url)s, %(care_text)s, %(country_of_origin)s,
                CURRENT_TIMESTAMP)
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
                last_seen_in_sitemap = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP;
        """, values)


def update_qfix_mapping(conn, brand, product_id, qfix_data):
    """Update the QFix mapping columns for a given product.

    qfix_data should be a dict with keys:
      qfix_clothing_type, qfix_clothing_type_id, qfix_material,
      qfix_material_id, qfix_url, qfix_url_repair, qfix_url_adjustment,
      qfix_url_care, qfix_url_other
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE products_unified
            SET qfix_clothing_type = %(qfix_clothing_type)s,
                qfix_clothing_type_id = %(qfix_clothing_type_id)s,
                qfix_material = %(qfix_material)s,
                qfix_material_id = %(qfix_material_id)s,
                qfix_url = %(qfix_url)s,
                qfix_url_repair = %(qfix_url_repair)s,
                qfix_url_adjustment = %(qfix_url_adjustment)s,
                qfix_url_care = %(qfix_url_care)s,
                qfix_url_other = %(qfix_url_other)s
            WHERE brand = %(brand)s AND product_id = %(product_id)s
        """, {
            "brand": brand,
            "product_id": product_id,
            "qfix_clothing_type": qfix_data.get("qfix_clothing_type"),
            "qfix_clothing_type_id": qfix_data.get("qfix_clothing_type_id"),
            "qfix_material": qfix_data.get("qfix_material"),
            "qfix_material_id": qfix_data.get("qfix_material_id"),
            "qfix_url": qfix_data.get("qfix_url"),
            "qfix_url_repair": qfix_data.get("qfix_url_repair"),
            "qfix_url_adjustment": qfix_data.get("qfix_url_adjustment"),
            "qfix_url_care": qfix_data.get("qfix_url_care"),
            "qfix_url_other": qfix_data.get("qfix_url_other"),
        })


def create_action_rankings_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS qfix_action_rankings (
                clothing_type_id INTEGER NOT NULL,
                material_id INTEGER NOT NULL,
                rankings JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (clothing_type_id, material_id)
            );
        """)


def upsert_action_ranking(conn, clothing_type_id, material_id, rankings):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO qfix_action_rankings (clothing_type_id, material_id, rankings)
            VALUES (%s, %s, %s)
            ON CONFLICT (clothing_type_id, material_id) DO UPDATE SET
                rankings = EXCLUDED.rankings,
                updated_at = CURRENT_TIMESTAMP;
        """, (clothing_type_id, material_id, json.dumps(rankings)))


def get_action_ranking(conn, clothing_type_id, material_id):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT rankings FROM qfix_action_rankings "
            "WHERE clothing_type_id = %s AND material_id = %s",
            (clothing_type_id, material_id),
        )
        row = cur.fetchone()
        if row:
            r = row["rankings"]
            return r if isinstance(r, dict) else json.loads(r)
        return None


# ── Robust scraper runner ──────────────────────────────────────────────

class _PersistentDB:
    """A DB handle that automatically reconnects on failure."""

    def __init__(self):
        self._conn = None

    def _ensure(self):
        if self._conn is not None:
            try:
                self._conn.cursor().execute("SELECT 1")
                return
            except Exception:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
        self._conn = _connect_with_retry(DATABASE_URL, retries=5, delay=2.0)

    def upsert(self, product):
        """Upsert a single product, reconnecting if needed. Returns True on success."""
        for attempt in range(3):
            try:
                self._ensure()
                upsert_product(self._conn, product)
                return True
            except Exception as e:
                logger.warning("DB upsert failed (attempt %d/3) for %s/%s: %s",
                               attempt + 1, product.get("brand"), product.get("product_id"), e)
                self._conn = None  # force reconnect
                if attempt < 2:
                    time.sleep(2 ** attempt)
        return False

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


def run_scraper(scrape_fn, brand, batch_size=50, log_every=100):
    """Shared robust scraper runner used by all brand main files.

    scrape_fn: a callable that accepts a callback(product_dict).
               The runner will call scrape_fn(on_product).
    brand:     the brand name to stamp on each product.

    Products are written to the DB one-at-a-time with auto-reconnect.
    Failed products are collected and retried once at the end.
    """
    db = _PersistentDB()
    lock = threading.Lock()
    saved = [0]
    failed = []

    def on_product(product):
        product["sub_brand"] = product.get("brand")
        product["brand"] = brand
        ok = db.upsert(product)
        with lock:
            if ok:
                saved[0] += 1
                if saved[0] % log_every == 0:
                    logger.info("Progress: %d products saved so far", saved[0])
            else:
                failed.append(product)

    scrape_fn(on_product)

    # Retry failed products once
    if failed:
        logger.info("Retrying %d failed products...", len(failed))
        retry_failed = []
        for p in failed:
            if db.upsert(p):
                saved[0] += 1
            else:
                retry_failed.append(p)
        if retry_failed:
            logger.error("%d products could not be saved after retries: %s",
                         len(retry_failed),
                         [f"{p.get('brand')}/{p.get('product_id')}" for p in retry_failed[:10]])

    db.close()
    logger.info("Done! Saved %d products total.", saved[0])
    return saved[0]
