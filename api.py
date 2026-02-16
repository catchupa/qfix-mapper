import os
import tempfile

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request

from mapping import map_product, map_clothing_type, map_material, QFIX_CLOTHING_TYPE_IDS, VALID_MATERIAL_IDS
from mapping_v2 import map_product_v2
from database import create_table_v2, upsert_product_v2, create_table_ginatricot, create_table_eton, DATABASE_URL
from protocol_parser import parse_protocol_xlsx
from vision import classify_and_map

app = Flask(__name__)


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# ── v1 endpoints (scraper-based) ─────────────────────────────────────────

@app.route("/product/<product_id>")
def get_product(product_id):
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM products WHERE product_id = %s",
            (product_id,),
        )
        row = cur.fetchone()
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM products ORDER BY product_id LIMIT 100"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin FROM products_v2 WHERE gtin = %s",
            (gtin,),
        )
        row = cur.fetchone()
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin FROM products_v2 WHERE article_number = %s ORDER BY size",
            (article_number,),
        )
        rows = cur.fetchall()
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT gtin, article_number, product_name, category, size, color, brand FROM products_v2 ORDER BY article_number, size LIMIT 200"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── Gina Tricot endpoints (scraper-based) ─────────────────────────────────

@app.route("/ginatricot/product/<product_id>")
def ginatricot_get_product(product_id):
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM ginatricot_products WHERE product_id = %s",
            (product_id,),
        )
        row = cur.fetchone()
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM ginatricot_products ORDER BY product_id LIMIT 100"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── v3 endpoints (Gina Tricot scraper data) ───────────────────────────────

@app.route("/v3/product/<product_id>")
def v3_get_product(product_id):
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM ginatricot_products WHERE product_id = %s",
            (product_id,),
        )
        row = cur.fetchone()
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, description, color, brand FROM ginatricot_products ORDER BY product_id LIMIT 200"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


@app.route("/v3/product/search")
def v3_search():
    """Search Gina Tricot scraped products by name."""
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "Provide ?q= search term"}), 400
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, color, brand FROM ginatricot_products WHERE product_name ILIKE %s ORDER BY product_id LIMIT 50",
            (f"%{q}%",),
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


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
    create_table_v2(conn)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get scraped data
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM ginatricot_products WHERE product_id = %s",
            (product_id,),
        )
        scraped_row = cur.fetchone()

        if not scraped_row:
            conn.close()
            return jsonify({"error": f"Product {product_id} not found"}), 404

        scraped = dict(scraped_row)

        # Try to find matching protocol data by product name
        cur.execute(
            "SELECT article_number, product_name, description, category, color, materials, care_text, brand, country_of_origin FROM products_v2 WHERE LOWER(product_name) = LOWER(%s) LIMIT 1",
            (scraped["product_name"],),
        )
        protocol_row = cur.fetchone()

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
    create_table_v2(conn)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
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
        """)
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


@app.route("/v4/product/search")
def v4_search():
    """Search aggregated Gina Tricot products by name."""
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "Provide ?q= search term"}), 400
    conn = get_db()
    create_table_v2(conn)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT
                g.product_id, g.product_name, g.category, g.clothing_type,
                g.color, g.brand,
                CASE WHEN p.article_number IS NOT NULL THEN 'merged' ELSE 'scraper_only' END AS source
            FROM ginatricot_products g
            LEFT JOIN (
                SELECT DISTINCT article_number, product_name
                FROM products_v2
            ) p ON LOWER(g.product_name) = LOWER(p.product_name)
            WHERE g.product_name ILIKE %s
            ORDER BY g.product_id
            LIMIT 50
        """, (f"%{q}%",))
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── Eton endpoints (scraper-based) ────────────────────────────────────────

@app.route("/eton/product/<product_id>")
def eton_get_product(product_id):
    conn = get_db()
    create_table_eton(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url FROM eton_products WHERE product_id = %s",
            (product_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = map_product(product)

    return jsonify({
        "eton": product,
        "qfix": qfix,
    })


@app.route("/eton/products")
def eton_list_products():
    conn = get_db()
    create_table_eton(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM eton_products ORDER BY product_id LIMIT 100"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── Vision identification endpoint ────────────────────────────────────────

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
    "image/jpg": "image/jpeg",
}


@app.route("/identify", methods=["POST"])
def identify():
    """Upload an image to identify the garment and get a QFix repair link."""
    if "image" not in request.files:
        return jsonify({"error": "No image provided. Use multipart form with key 'image'."}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    media_type = ALLOWED_IMAGE_TYPES.get(file.content_type)
    if not media_type:
        return jsonify({"error": f"Unsupported image type: {file.content_type}. Use JPEG, PNG, WebP, or GIF."}), 400

    image_bytes = file.read()
    if len(image_bytes) > 20 * 1024 * 1024:  # 20MB limit
        return jsonify({"error": "Image too large (max 20MB)"}), 400

    try:
        result = classify_and_map(image_bytes, media_type)
    except Exception as e:
        return jsonify({"error": f"Vision API error: {e}"}), 500

    return jsonify(result)


# ── Unmapped categories endpoint ──────────────────────────────────────────

@app.route("/unmapped")
def unmapped_categories():
    """Return all clothing types and materials that don't map to QFix, grouped by brand."""
    conn = get_db()

    result = {}

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # KappAhl unmapped
        cur.execute(
            "SELECT DISTINCT clothing_type, material_composition, category FROM products WHERE clothing_type IS NOT NULL ORDER BY clothing_type"
        )
        kappahl_rows = cur.fetchall()

        kappahl_unmapped_types = {}
        kappahl_unmapped_materials = set()
        for row in kappahl_rows:
            ct = row["clothing_type"]
            mat = row["material_composition"]
            mapped_type = map_clothing_type(ct)
            if mapped_type is None and ct:
                if ct not in kappahl_unmapped_types:
                    kappahl_unmapped_types[ct] = 0
                kappahl_unmapped_types[ct] += 1
            mapped_mat = map_material(mat)
            if mapped_mat == "Other/Unsure" and mat:
                kappahl_unmapped_materials.add(mat)

        result["kappahl"] = {
            "unmapped_clothing_types": [
                {"clothing_type": ct, "distinct_products": count}
                for ct, count in sorted(kappahl_unmapped_types.items())
            ],
            "unmapped_materials": sorted(kappahl_unmapped_materials),
        }

        # Gina Tricot unmapped
        try:
            cur.execute(
                "SELECT DISTINCT clothing_type, material_composition, category FROM ginatricot_products WHERE clothing_type IS NOT NULL ORDER BY clothing_type"
            )
            gt_rows = cur.fetchall()
        except Exception:
            gt_rows = []

        gt_unmapped_types = {}
        gt_unmapped_materials = set()
        for row in gt_rows:
            ct = row["clothing_type"]
            mat = row["material_composition"]
            mapped_type = map_clothing_type(ct)
            if mapped_type is None and ct:
                if ct not in gt_unmapped_types:
                    gt_unmapped_types[ct] = 0
                gt_unmapped_types[ct] += 1
            mapped_mat = map_material(mat)
            if mapped_mat == "Other/Unsure" and mat:
                gt_unmapped_materials.add(mat)

        result["ginatricot"] = {
            "unmapped_clothing_types": [
                {"clothing_type": ct, "distinct_products": count}
                for ct, count in sorted(gt_unmapped_types.items())
            ],
            "unmapped_materials": sorted(gt_unmapped_materials),
        }

    # Also include reference: valid QFix categories for mapping
    result["qfix_valid_clothing_types"] = {name: id for name, id in sorted(QFIX_CLOTHING_TYPE_IDS.items())}
    result["qfix_valid_materials"] = {
        ct_id: {str(mat_id): mat_name for mat_id, mat_name in mats.items()}
        for ct_id, mats in VALID_MATERIAL_IDS.items()
    }

    conn.close()
    return jsonify(result)


@app.route("/unmapped/add", methods=["POST"])
def add_mapping():
    """Add a new clothing type or material mapping.

    JSON body:
      {"type": "clothing_type", "from": "kjolar > langkjolar", "to": "Skirt / Dress"}
      {"type": "material", "from": "neopren", "to": "Standard textile"}
    """
    from mapping import CLOTHING_TYPE_MAP, MATERIAL_MAP

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    mapping_type = data.get("type")
    from_val = data.get("from", "").strip().lower()
    to_val = data.get("to", "").strip()

    if not mapping_type or not from_val or not to_val:
        return jsonify({"error": "Required fields: type, from, to"}), 400

    if mapping_type == "clothing_type":
        if to_val not in QFIX_CLOTHING_TYPE_IDS:
            return jsonify({
                "error": f"Invalid QFix clothing type: '{to_val}'",
                "valid_types": sorted(QFIX_CLOTHING_TYPE_IDS.keys()),
            }), 400
        CLOTHING_TYPE_MAP[from_val] = to_val
        return jsonify({"status": "ok", "mapped": f"'{from_val}' -> '{to_val}' (id={QFIX_CLOTHING_TYPE_IDS[to_val]})"})

    elif mapping_type == "material":
        valid_materials = {"Standard textile", "Linen/Wool", "Cashmere", "Silk", "Leather/Suede", "Down", "Fur", "Other/Unsure"}
        if to_val not in valid_materials:
            return jsonify({
                "error": f"Invalid QFix material: '{to_val}'",
                "valid_materials": sorted(valid_materials),
            }), 400
        MATERIAL_MAP[from_val] = to_val
        return jsonify({"status": "ok", "mapped": f"'{from_val}' -> '{to_val}'"})

    else:
        return jsonify({"error": "type must be 'clothing_type' or 'material'"}), 400


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    # Re-read DATABASE_URL after loading .env
    import database
    database.DATABASE_URL = os.environ.get("DATABASE_URL")
    app.run(debug=True, port=8000)
