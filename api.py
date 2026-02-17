import os
import tempfile

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request
from flasgger import Swagger

from mapping import map_product, map_clothing_type, map_material, QFIX_CLOTHING_TYPE_IDS, VALID_MATERIAL_IDS
from mapping_v2 import map_product_v2
from database import create_table_v2, upsert_product_v2, create_table_ginatricot, create_table_eton, create_table_nudie, create_table_lindex, DATABASE_URL
from protocol_parser import parse_protocol_xlsx
from vision import classify_and_map

app = Flask(__name__)

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}

swagger_template = {
    "info": {
        "title": "QFix Product API",
        "description": "Maps products from Swedish clothing brands (KappAhl, Gina Tricot, Eton, Nudie Jeans, Lindex) to QFix repair service categories.",
        "version": "1.0",
    },
    "basePath": "/",
    "schemes": ["https", "http"],
    "tags": [
        {"name": "KappAhl", "description": "KappAhl product endpoints"},
        {"name": "Gina Tricot", "description": "Gina Tricot product endpoints"},
        {"name": "Eton", "description": "Eton product endpoints"},
        {"name": "Nudie Jeans", "description": "Nudie Jeans product endpoints"},
        {"name": "Lindex", "description": "Lindex product endpoints"},
        {"name": "T4V Protocol", "description": "T4V protocol data endpoints"},
        {"name": "Aggregated", "description": "Merged scraper + protocol data"},
        {"name": "Vision", "description": "Image-based garment identification"},
        {"name": "Mapping", "description": "Unmapped categories and mapping management"},
    ],
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# ── v1 endpoints (scraper-based) ─────────────────────────────────────────

@app.route("/product/<product_id>")
@app.route("/kappahl/product/<product_id>")
def get_product(product_id):
    """Look up a KappAhl product by ID with QFix mapping.
    ---
    tags:
      - KappAhl
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: KappAhl product ID
    responses:
      200:
        description: Product data with QFix repair category mapping
      404:
        description: Product not found
    """
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
@app.route("/kappahl/products")
def list_products():
    """List KappAhl products (limit 100).
    ---
    tags:
      - KappAhl
    responses:
      200:
        description: Array of KappAhl products
    """
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
    """Upload a T4V protocol xlsx file.
    ---
    tags:
      - T4V Protocol
    consumes:
      - multipart/form-data
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: T4V protocol .xlsx file
    responses:
      200:
        description: Import result with product count
      400:
        description: Invalid file or parse error
    """
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
    """Look up a product by GTIN barcode.
    ---
    tags:
      - T4V Protocol
    parameters:
      - name: gtin
        in: path
        type: string
        required: true
        description: GTIN barcode (13 digits)
    responses:
      200:
        description: Product data with QFix mapping
      404:
        description: GTIN not found
    """
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
    """Look up all size variants for an article number.
    ---
    tags:
      - T4V Protocol
    parameters:
      - name: article_number
        in: path
        type: string
        required: true
        description: Article number
    responses:
      200:
        description: Article with all size variants and QFix mapping
      404:
        description: Article not found
    """
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
    """List T4V protocol products (limit 200).
    ---
    tags:
      - T4V Protocol
    responses:
      200:
        description: Array of protocol products
    """
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
    """Look up a Gina Tricot product by ID with QFix mapping.
    ---
    tags:
      - Gina Tricot
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Gina Tricot product ID
    responses:
      200:
        description: Product data with QFix mapping
      404:
        description: Product not found
    """
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
    """List Gina Tricot products (limit 100).
    ---
    tags:
      - Gina Tricot
    responses:
      200:
        description: Array of Gina Tricot products
    """
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
    """Look up a Gina Tricot product (legacy v3 format).
    ---
    tags:
      - Gina Tricot
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Gina Tricot product ID
    responses:
      200:
        description: Product data with QFix mapping
      404:
        description: Product not found
    """
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
    """List Gina Tricot products (legacy v3, limit 200).
    ---
    tags:
      - Gina Tricot
    responses:
      200:
        description: Array of Gina Tricot products
    """
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
    """Search Gina Tricot products by name.
    ---
    tags:
      - Gina Tricot
    parameters:
      - name: q
        in: query
        type: string
        required: true
        description: Search term (matched against product name)
    responses:
      200:
        description: Array of matching products
      400:
        description: Missing search term
    """
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
    """Get a Gina Tricot product with merged scraper + protocol data.
    ---
    tags:
      - Aggregated
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Gina Tricot product ID
    responses:
      200:
        description: Merged product data (source is 'merged' or 'scraper_only')
      404:
        description: Product not found
    """
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
    """List aggregated Gina Tricot products (limit 200).
    ---
    tags:
      - Aggregated
    responses:
      200:
        description: Array of products with merge status
    """
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
    """Search aggregated Gina Tricot products by name.
    ---
    tags:
      - Aggregated
    parameters:
      - name: q
        in: query
        type: string
        required: true
        description: Search term
    responses:
      200:
        description: Array of matching products with merge status
      400:
        description: Missing search term
    """
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
    """Look up an Eton product by ID with QFix mapping.
    ---
    tags:
      - Eton
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Eton product ID
    responses:
      200:
        description: Product data with QFix mapping
      404:
        description: Product not found
    """
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
    """List Eton products (limit 100).
    ---
    tags:
      - Eton
    responses:
      200:
        description: Array of Eton products
    """
    conn = get_db()
    create_table_eton(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM eton_products ORDER BY product_id LIMIT 100"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── Lindex endpoints (scraper-based) ──────────────────────────────────────

@app.route("/lindex/product/<product_id>")
def lindex_get_product(product_id):
    """Look up a Lindex product by ID with QFix mapping.
    ---
    tags:
      - Lindex
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Lindex product ID (styleId)
    responses:
      200:
        description: Product data with QFix mapping
      404:
        description: Product not found
    """
    conn = get_db()
    create_table_lindex(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url FROM lindex_products WHERE product_id = %s",
            (product_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = map_product(product)

    return jsonify({
        "lindex": product,
        "qfix": qfix,
    })


@app.route("/lindex/products")
def lindex_list_products():
    """List Lindex products (limit 100).
    ---
    tags:
      - Lindex
    responses:
      200:
        description: Array of Lindex products
    """
    conn = get_db()
    create_table_lindex(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM lindex_products ORDER BY product_id LIMIT 100"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── Nudie Jeans endpoints (scraper-based) ─────────────────────────────────

@app.route("/nudie/product/<product_id>")
def nudie_get_product(product_id):
    """Look up a Nudie Jeans product by ID with QFix mapping.
    ---
    tags:
      - Nudie Jeans
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Nudie Jeans product ID
    responses:
      200:
        description: Product data with QFix mapping
      404:
        description: Product not found
    """
    conn = get_db()
    create_table_nudie(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand, image_url FROM nudie_products WHERE product_id = %s",
            (product_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = map_product(product)

    return jsonify({
        "nudie": product,
        "qfix": qfix,
    })


@app.route("/nudie/products")
def nudie_list_products():
    """List Nudie Jeans products (limit 100).
    ---
    tags:
      - Nudie Jeans
    responses:
      200:
        description: Array of Nudie Jeans products
    """
    conn = get_db()
    create_table_nudie(conn)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, description, color, brand FROM nudie_products ORDER BY product_id LIMIT 100"
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
    """Upload a garment image for identification and QFix mapping.
    ---
    tags:
      - Vision
    consumes:
      - multipart/form-data
    parameters:
      - name: image
        in: formData
        type: file
        required: true
        description: Garment image (JPEG, PNG, WebP, or GIF, max 20 MB)
    responses:
      200:
        description: Classification result with QFix repair category mapping
      400:
        description: Missing or invalid image
      500:
        description: Vision API error
    """
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
    """Get all unmapped clothing types and materials across all brands.
    ---
    tags:
      - Mapping
    responses:
      200:
        description: Unmapped categories per brand plus valid QFix reference data
    """
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

        # Eton unmapped
        try:
            cur.execute(
                "SELECT DISTINCT clothing_type, material_composition, category FROM eton_products WHERE clothing_type IS NOT NULL ORDER BY clothing_type"
            )
            eton_rows = cur.fetchall()
        except Exception:
            eton_rows = []

        eton_unmapped_types = {}
        eton_unmapped_materials = set()
        for row in eton_rows:
            ct = row["clothing_type"]
            mat = row["material_composition"]
            mapped_type = map_clothing_type(ct)
            if mapped_type is None and ct:
                if ct not in eton_unmapped_types:
                    eton_unmapped_types[ct] = 0
                eton_unmapped_types[ct] += 1
            mapped_mat = map_material(mat)
            if mapped_mat == "Other/Unsure" and mat:
                eton_unmapped_materials.add(mat)

        result["eton"] = {
            "unmapped_clothing_types": [
                {"clothing_type": ct, "distinct_products": count}
                for ct, count in sorted(eton_unmapped_types.items())
            ],
            "unmapped_materials": sorted(eton_unmapped_materials),
        }

        # Nudie unmapped
        try:
            cur.execute(
                "SELECT DISTINCT clothing_type, material_composition, category FROM nudie_products WHERE clothing_type IS NOT NULL ORDER BY clothing_type"
            )
            nudie_rows = cur.fetchall()
        except Exception:
            nudie_rows = []

        nudie_unmapped_types = {}
        nudie_unmapped_materials = set()
        for row in nudie_rows:
            ct = row["clothing_type"]
            mat = row["material_composition"]
            mapped_type = map_clothing_type(ct)
            if mapped_type is None and ct:
                if ct not in nudie_unmapped_types:
                    nudie_unmapped_types[ct] = 0
                nudie_unmapped_types[ct] += 1
            mapped_mat = map_material(mat)
            if mapped_mat == "Other/Unsure" and mat:
                nudie_unmapped_materials.add(mat)

        result["nudie"] = {
            "unmapped_clothing_types": [
                {"clothing_type": ct, "distinct_products": count}
                for ct, count in sorted(nudie_unmapped_types.items())
            ],
            "unmapped_materials": sorted(nudie_unmapped_materials),
        }

        # Lindex unmapped
        try:
            cur.execute(
                "SELECT DISTINCT clothing_type, material_composition, category FROM lindex_products WHERE clothing_type IS NOT NULL ORDER BY clothing_type"
            )
            lindex_rows = cur.fetchall()
        except Exception:
            lindex_rows = []

        lindex_unmapped_types = {}
        lindex_unmapped_materials = set()
        for row in lindex_rows:
            ct = row["clothing_type"]
            mat = row["material_composition"]
            mapped_type = map_clothing_type(ct)
            if mapped_type is None and ct:
                if ct not in lindex_unmapped_types:
                    lindex_unmapped_types[ct] = 0
                lindex_unmapped_types[ct] += 1
            mapped_mat = map_material(mat)
            if mapped_mat == "Other/Unsure" and mat:
                lindex_unmapped_materials.add(mat)

        result["lindex"] = {
            "unmapped_clothing_types": [
                {"clothing_type": ct, "distinct_products": count}
                for ct, count in sorted(lindex_unmapped_types.items())
            ],
            "unmapped_materials": sorted(lindex_unmapped_materials),
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
    """Add a new clothing type or material mapping (in-memory, resets on redeploy).
    ---
    tags:
      - Mapping
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - type
            - from
            - to
          properties:
            type:
              type: string
              enum: [clothing_type, material]
              description: Type of mapping to add
            from:
              type: string
              description: Source value (e.g. "coatsjackets > kappor")
            to:
              type: string
              description: Target QFix category (e.g. "Coat")
    responses:
      200:
        description: Mapping added successfully
      400:
        description: Invalid input or unknown target category
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
