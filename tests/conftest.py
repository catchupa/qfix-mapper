import json
import html
import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def db_conn():
    """In-memory SQLite connection with all tables created."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from database import create_table, create_table_v2, create_table_ginatricot
    create_table(conn)
    create_table_v2(conn)
    create_table_ginatricot(conn)
    yield conn
    conn.close()


@pytest.fixture
def app_client(tmp_path):
    """Flask test client with a temporary database."""
    db_file = str(tmp_path / "test.db")
    os.environ["DB_PATH"] = db_file

    # Re-import to pick up the new DB_PATH
    import importlib
    import api as api_module
    importlib.reload(api_module)

    api_module.DB_PATH = db_file
    api_module.app.config["TESTING"] = True

    # Create tables
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    from database import create_table, create_table_v2, create_table_ginatricot
    create_table(conn)
    create_table_v2(conn)
    create_table_ginatricot(conn)
    conn.close()

    with api_module.app.test_client() as client:
        yield client, db_file


def _make_kappahl_html(
    name="Bootcut jeans",
    description="Jeans i rak passform",
    brand_name="Xlnt",
    color_text="Svart / enfärgad",
    material_desc="Huvudmaterial: 75% Bomull, 21% Polyester, 4% Elastan",
    breadcrumbs=None,
):
    """Build a fake KappAhl product page HTML."""
    product_json = json.dumps({
        "@context": "http://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "brand": {"@type": "Brand", "name": brand_name},
    })

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
    # Gina Tricot HTML-encodes the JSON-LD
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
