import json
import html
import os
import sqlite3
import tempfile

import pytest


def _create_tables_sqlite(conn):
    """Create the unified table using SQLite-compatible SQL."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products_unified (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.commit()


@pytest.fixture
def db_conn():
    """In-memory SQLite connection with products_unified table created."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _create_tables_sqlite(conn)
    yield conn
    conn.close()


@pytest.fixture
def app_client(tmp_path):
    """Flask test client with a temporary SQLite database.

    Patches the api module to use SQLite instead of Postgres for testing.
    """
    db_file = str(tmp_path / "test.db")

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    _create_tables_sqlite(conn)
    conn.close()

    import api as api_module
    from unittest.mock import patch
    from psycopg2.extras import RealDictCursor

    class _SqliteRealDictCursor:
        """Adapter to make SQLite cursor behave like psycopg2 RealDictCursor."""
        def __init__(self, conn):
            self._conn = conn
            self._cursor = conn.cursor()

        def execute(self, query, params=None):
            query = query.replace("%s", "?")
            query = query.replace("ILIKE", "LIKE")
            if params:
                self._cursor.execute(query, params)
            else:
                self._cursor.execute(query)

        def fetchone(self):
            row = self._cursor.fetchone()
            if row is None:
                return None
            return dict(row)

        def fetchall(self):
            return [dict(r) for r in self._cursor.fetchall()]

        def close(self):
            try:
                self._cursor.close()
            except Exception:
                pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    class _SqliteConnection:
        """Adapter to make SQLite connection behave like psycopg2 connection."""
        def __init__(self, db_path):
            self._conn = sqlite3.connect(db_path)
            self._conn.row_factory = sqlite3.Row
            self.autocommit = True

        def cursor(self, cursor_factory=None):
            return _SqliteRealDictCursor(self._conn)

        def close(self):
            self._conn.close()

    def _mock_get_db():
        return _SqliteConnection(db_file)

    def _noop(conn):
        pass

    api_module.app.config["TESTING"] = True
    with patch.object(api_module, "get_db", _mock_get_db), \
         patch.object(api_module, "create_table", _noop):
        with api_module.app.test_client() as client:
            yield client, db_file


def _make_kappahl_html(
    name="Bootcut jeans",
    description="Jeans i rak passform",
    brand_name="Xlnt",
    color_text="Svart / enfärgad",
    material_desc="Huvudmaterial: 75% Bomull, 21% Polyester, 4% Elastan",
    breadcrumbs=None,
    image_url="https://static.kappahl.com/productimages/131367_f_4.jpg",
):
    """Build a fake KappAhl product page HTML."""
    product_data = {
        "@context": "http://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "brand": {"@type": "Brand", "name": brand_name},
    }
    if image_url:
        product_data["image"] = [image_url]
    product_json = json.dumps(product_data)

    breadcrumb_html = ""
    if breadcrumbs:
        items = "".join(f'<a>{b}</a>' for b in breadcrumbs)
        breadcrumb_html = f'<nav aria-label="breadcrumb">{items}</nav>'

    return f"""
    <html><head>
    <script type="application/ld+json">{product_json}</script>
    </head><body>
    {breadcrumb_html}
    <h1>{name}</h1>
    <p>Färg: {color_text} Storlek S M L</p>
    <script>
    var productData = {{"materialDescriptions": ["{material_desc}"]}};
    </script>
    </body></html>
    """


def _make_ginatricot_html(
    name="Structure maxi skirt",
    description="Lågmidjad långkjol",
    brand="Gina Tricot",
    color="Black (9000)",
    material="Bomull 57%, Polyamid 42%, Elastan 1%",
    image_url="https://ginatricot-pim.imgix.net/225549000/22554900001.jpg",
):
    """Build a fake Gina Tricot product page with HTML-encoded JSON-LD."""
    product_data = {
        "@context": "http://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "brand": brand,
        "color": color,
        "material": material,
        "mpn": "225549000",
    }
    if image_url:
        product_data["image"] = [image_url]
    encoded = html.escape(json.dumps(product_data))

    return f"""
    <html><head>
    <script type="application/ld+json">{encoded}</script>
    </head><body>
    <h1>{name}</h1>
    </body></html>
    """


@pytest.fixture
def sample_kappahl_html():
    return _make_kappahl_html


@pytest.fixture
def sample_ginatricot_html():
    return _make_ginatricot_html
