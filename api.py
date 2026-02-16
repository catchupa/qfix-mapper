import os
import sqlite3
import tempfile

from flask import Flask, jsonify, request

from mapping import map_product
from mapping_v2 import map_product_v2
from database import create_table_v2, upsert_product_v2
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
        "SELECT product_id, product_name, category, clothing_type, material_composition, product_url FROM products WHERE product_id = ?",
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
        "SELECT product_id, product_name, category, clothing_type FROM products ORDER BY product_id LIMIT 100"
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


if __name__ == "__main__":
    app.run(debug=True, port=8000)
