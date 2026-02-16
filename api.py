import os
import sqlite3
import tempfile

from flask import Flask, jsonify, request

from mapping import map_product
from mapping_v2 import map_product_v2
from database import create_table_v2, upsert_product_v2, migrate_products_table, create_table_ginatricot
from protocol_parser import parse_protocol_xlsx

app = Flask(__name__)
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "products.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── v1 endpoints (scraper-based) ─────────────────────────────────────────

@app.route("/product/<product_id>")
def get_product(product_id):
    conn = get_db()
    row = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM products WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = map_product(product)

    return jsonify({
        "kappahl": product,
        "qfix": qfix,
    })


@app.route("/products")
def list_products():
    conn = get_db()
    rows = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM products ORDER BY product_id LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── v2 endpoints (T4V protocol xlsx) ─────────────────────────────────────

@app.route("/v2/upload", methods=["POST"])
def v2_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided. Use multipart form with key 'file'."}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".xlsx"):
        return jsonify({"error": "File must be an .xlsx file"}), 400

    # Save to temp file for openpyxl to read
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        products = parse_protocol_xlsx(tmp_path)
    except Exception as e:
        os.unlink(tmp_path)
        return jsonify({"error": f"Failed to parse xlsx: {e}"}), 400
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    conn = get_db()
    create_table_v2(conn)
    count = 0
    for prod in products:
        upsert_product_v2(conn, prod)
        count += 1
    conn.close()

    return jsonify({"status": "ok", "products_imported": count})


@app.route("/v2/product/gtin/<gtin>")
def v2_get_by_gtin(gtin):
    conn = get_db()
    create_table_v2(conn)
    row = conn.execute(
        "SELECT gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin FROM products_v2 WHERE gtin = ?",
        (gtin,),
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"GTIN {gtin} not found"}), 404

    product = dict(row)
    qfix = map_product_v2(product)

    return jsonify({
        "product": product,
        "qfix": qfix,
    })


@app.route("/v2/product/article/<article_number>")
def v2_get_by_article(article_number):
    conn = get_db()
    create_table_v2(conn)
    rows = conn.execute(
        "SELECT gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin FROM products_v2 WHERE article_number = ? ORDER BY size",
        (article_number,),
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": f"Article {article_number} not found"}), 404

    products = [dict(r) for r in rows]
    # QFix mapping is the same for all size variants — use first row
    qfix = map_product_v2(products[0])

    return jsonify({
        "article_number": article_number,
        "product_name": products[0]["product_name"],
        "variants": products,
        "qfix": qfix,
    })


@app.route("/v2/products")
def v2_list_products():
    conn = get_db()
    create_table_v2(conn)
    rows = conn.execute(
        "SELECT gtin, article_number, product_name, category, size, color, brand FROM products_v2 ORDER BY article_number, size LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── Gina Tricot endpoints (scraper-based) ─────────────────────────────────

@app.route("/ginatricot/product/<product_id>")
def ginatricot_get_product(product_id):
    conn = get_db()
    create_table_ginatricot(conn)
    row = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM ginatricot_products WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = map_product(product)

    return jsonify({
        "ginatricot": product,
        "qfix": qfix,
    })


@app.route("/ginatricot/products")
def ginatricot_list_products():
    conn = get_db()
    create_table_ginatricot(conn)
    rows = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM ginatricot_products ORDER BY product_id LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── v3 endpoints (Gina Tricot scraper data) ───────────────────────────────

@app.route("/v3/product/<product_id>")
def v3_get_product(product_id):
    conn = get_db()
    create_table_ginatricot(conn)
    row = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM ginatricot_products WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = map_product(product)

    return jsonify({
        "product": product,
        "qfix": qfix,
    })


@app.route("/v3/products")
def v3_list_products():
    conn = get_db()
    create_table_ginatricot(conn)
    rows = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, material_composition, description, color, brand FROM ginatricot_products ORDER BY product_id LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/v3/product/search")
def v3_search():
    """Search Gina Tricot scraped products by name."""
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "Provide ?q= search term"}), 400
    conn = get_db()
    create_table_ginatricot(conn)
    rows = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, color, brand FROM ginatricot_products WHERE product_name LIKE ? ORDER BY product_id LIMIT 50",
        (f"%{q}%",),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── v4 endpoints (aggregated: scraper + protocol merged) ──────────────────

def _merge_product(scraped, protocol):
    """Merge scraped and protocol data, preferring protocol for richer fields."""
    import json as _json

    merged = {
        "product_name": scraped.get("product_name") or protocol.get("product_name"),
        "brand": scraped.get("brand") or protocol.get("brand"),
        "color": protocol.get("color") or scraped.get("color"),
        "description_sv": scraped.get("description"),
        "description_en": protocol.get("description"),
        "category_scraped": scraped.get("category"),
        "category_protocol": protocol.get("category"),
        "clothing_type": scraped.get("clothing_type"),
        "material_composition": scraped.get("material_composition"),
        "materials_structured": protocol.get("materials"),
        "care_text": protocol.get("care_text"),
        "country_of_origin": protocol.get("country_of_origin"),
        "product_url": scraped.get("product_url"),
        "product_id": scraped.get("product_id"),
        "article_number": protocol.get("article_number"),
        "source": "merged",
    }

    # Parse structured materials for QFix mapping if available
    materials_list = None
    raw = protocol.get("materials")
    if raw and isinstance(raw, str):
        try:
            materials_list = _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            pass

    return merged, materials_list


@app.route("/v4/product/<product_id>")
def v4_get_product(product_id):
    """Get a Gina Tricot product with aggregated data from scraper + protocol."""
    conn = get_db()
    create_table_ginatricot(conn)
    create_table_v2(conn)

    # Get scraped data
    scraped_row = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM ginatricot_products WHERE product_id = ?",
        (product_id,),
    ).fetchone()

    if not scraped_row:
        conn.close()
        return jsonify({"error": f"Product {product_id} not found"}), 404

    scraped = dict(scraped_row)

    # Try to find matching protocol data by product name
    protocol = None
    protocol_row = conn.execute(
        "SELECT article_number, product_name, description, category, color, materials, care_text, brand, country_of_origin FROM products_v2 WHERE LOWER(product_name) = LOWER(?) LIMIT 1",
        (scraped["product_name"],),
    ).fetchone()
    conn.close()

    if protocol_row:
        protocol = dict(protocol_row)
        merged, materials_list = _merge_product(scraped, protocol)
        # Use v2 mapping (English materials + category) when protocol data exists
        qfix = map_product_v2(protocol, materials=materials_list)
    else:
        merged = {**scraped, "source": "scraper_only"}
        qfix = map_product(scraped)

    return jsonify({
        "product": merged,
        "qfix": qfix,
    })


@app.route("/v4/products")
def v4_list_products():
    """List Gina Tricot products, enriched with protocol data where available."""
    conn = get_db()
    create_table_ginatricot(conn)
    create_table_v2(conn)

    rows = conn.execute("""
        SELECT
            g.product_id, g.product_name, g.category, g.clothing_type,
            g.material_composition, g.description, g.color, g.brand,
            p.article_number AS protocol_article,
            p.category AS protocol_category,
            p.care_text, p.country_of_origin,
            CASE WHEN p.article_number IS NOT NULL THEN 'merged' ELSE 'scraper_only' END AS source
        FROM ginatricot_products g
        LEFT JOIN (
            SELECT DISTINCT article_number, product_name, category, care_text, country_of_origin
            FROM products_v2
        ) p ON LOWER(g.product_name) = LOWER(p.product_name)
        ORDER BY g.product_id
        LIMIT 200
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/v4/product/search")
def v4_search():
    """Search aggregated Gina Tricot products by name."""
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "Provide ?q= search term"}), 400
    conn = get_db()
    create_table_ginatricot(conn)
    create_table_v2(conn)

    rows = conn.execute("""
        SELECT
            g.product_id, g.product_name, g.category, g.clothing_type,
            g.color, g.brand,
            CASE WHEN p.article_number IS NOT NULL THEN 'merged' ELSE 'scraper_only' END AS source
        FROM ginatricot_products g
        LEFT JOIN (
            SELECT DISTINCT article_number, product_name
            FROM products_v2
        ) p ON LOWER(g.product_name) = LOWER(p.product_name)
        WHERE g.product_name LIKE ?
        ORDER BY g.product_id
        LIMIT 50
    """, (f"%{q}%",)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    # Run migration to add new columns to existing DB
    _conn = get_db()
    migrate_products_table(_conn)
    _conn.close()
    app.run(debug=True, port=8000)
