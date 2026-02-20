import json
import logging
import os
import tempfile
import time as _time

import anthropic
import psycopg2
import requests as http_requests
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger

from mapping import (
    map_product, map_product_legacy, map_clothing_type, map_material,
    map_category, _resolve_clothing_type_id, _resolve_material_id,
    QFIX_CLOTHING_TYPE_IDS, VALID_MATERIAL_IDS,
    CLOTHING_TYPE_MAP, MATERIAL_MAP, _KEYWORD_CLOTHING_MAP,
    BRAND_CLOTHING_TYPE_OVERRIDES, BRAND_KEYWORD_CLOTHING_OVERRIDES,
    BRAND_MATERIAL_OVERRIDES,
)
from mapping_v2 import map_product_v2
from database import create_table, upsert_product, update_qfix_mapping, DATABASE_URL, DATABASE_WRITE_URL
from protocol_parser import parse_protocol_xlsx
from vision import classify_and_map

app = Flask(__name__)
CORS(app)


# ── Rate limiting ─────────────────────────────────────────────────────────
def _rate_limit_key():
    """Use API key if provided, otherwise fall back to IP address."""
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return "key:" + api_key
    return "ip:" + get_remote_address()


limiter = Limiter(
    app=app,
    key_func=_rate_limit_key,
    default_limits=["100 per minute", "1000 per hour"],
    storage_uri="memory://",
)

# ── API key authentication ────────────────────────────────────────────────
# Format: "brand1:key1,brand2:key2"  — if unset, auth is disabled.
_api_keys = {}
_raw_keys = os.environ.get("API_KEYS", "")
if _raw_keys:
    for pair in _raw_keys.split(","):
        pair = pair.strip()
        if ":" in pair:
            slug, key = pair.split(":", 1)
            _api_keys[slug.strip()] = key.strip()


def _check_api_key(brand_slug):
    """Return an error response if API key auth is enabled and the key is invalid.
    Returns None when the request is authorized."""
    if not _api_keys:
        return None  # auth disabled
    expected = _api_keys.get(brand_slug)
    if not expected:
        return None  # no key configured for this brand
    provided = request.headers.get("X-API-Key", "")
    if provided != expected:
        return jsonify({"error": "Invalid or missing API key"}), 401
    return None

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
        "version": "2.0",
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
        {"name": "Redirect", "description": "QFix booking page redirects"},
        {"name": "Mapping", "description": "Unmapped categories, mapping management, and batch persistence"},
    ],
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

logger = logging.getLogger(__name__)


# ── Request logging ───────────────────────────────────────────────────────
@app.before_request
def _log_request_start():
    request._start_time = _time.time()


@app.after_request
def _log_request(response):
    duration_ms = (_time.time() - getattr(request, "_start_time", _time.time())) * 1000
    logger.info("%s %s %s %.1fms", request.method, request.path,
                response.status_code, duration_ms)
    # Add Cache-Control for read-only GET product endpoints
    if (request.method == "GET" and response.status_code == 200
            and request.path not in ("/health", "/apidocs/", "/apispec.json")):
        if "/product/" in request.path:
            response.headers.setdefault("Cache-Control", "public, max-age=600")
        elif "/products" in request.path:
            response.headers.setdefault("Cache-Control", "public, max-age=300")
    return response


# ── QFix catalog cache ────────────────────────────────────────────────────

QFIX_CATEGORIES_URL = "https://dev.qfixr.me/wp-json/qfix/v1/product-categories?parent=23"
# Metadata from product-categories (L3 items, L4 subitems, services)
_qfix_items = {}      # L3 clothing types: {id: {name, slug, link, parent}}
_qfix_subitems = {}   # L4 materials:      {id: {name, slug, link}}
_qfix_services = {}   # {(L3_id, L4_id): [service_categories]}
_qfix_catalog_loaded = False


def _build_catalog_node(node):
    """Extract the fields we want from a QFix catalog node."""
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "slug": node.get("slug"),
        "link": node.get("link"),
        "description": node.get("category_description") or None,
    }


def _load_qfix_catalog():
    """Fetch the QFix category tree and build lookup dicts.

    The tree structure is:
      L1 (Clothing/Shoes/Bags) → L2 (Women's/Men's/...) → L3 (Shirt/Trousers/...)
        → L4 (Standard textile/Leather/...) → L5 (Repair/Adjust/Washing/Other)
          → Products (services) → Variants
    """
    global _qfix_items, _qfix_subitems, _qfix_catalog_loaded, _qfix_services
    if _qfix_catalog_loaded:
        return
    try:
        resp = http_requests.get(QFIX_CATEGORIES_URL, timeout=30)
        resp.raise_for_status()
        tree = resp.json()
    except Exception as e:
        logger.warning("Failed to fetch QFix catalog: %s", e)
        return

    for l1 in tree:
        for l2 in l1.get("children", []):
            for l3 in l2.get("children", []):
                l3_id = l3.get("id")
                if l3_id not in _qfix_items:
                    _qfix_items[l3_id] = {
                        **_build_catalog_node(l3),
                        "parent": _build_catalog_node(l2),
                    }
                for l4 in l3.get("children", []):
                    l4_id = l4.get("id")
                    if l4_id not in _qfix_subitems:
                        _qfix_subitems[l4_id] = _build_catalog_node(l4)

                    # Extract services grouped by L5 service category
                    service_categories = []
                    for l5 in l4.get("children", []):
                        svc_cat = {
                            "id": l5.get("id"),
                            "name": l5.get("name"),
                            "slug": l5.get("slug"),
                            "services": [],
                        }
                        for prod in l5.get("products", []):
                            service = {
                                "id": prod.get("id"),
                                "name": prod.get("name"),
                                "price": prod.get("price"),
                                "variants": [
                                    {
                                        "id": v.get("id"),
                                        "name": v.get("name"),
                                        "price": v.get("price"),
                                    }
                                    for v in prod.get("variants", [])
                                ],
                            }
                            svc_cat["services"].append(service)
                        service_categories.append(svc_cat)
                    _qfix_services[(l3_id, l4_id)] = service_categories

    _qfix_catalog_loaded = True
    logger.info("QFix catalog loaded: %d items, %d subitems, %d service combos",
                len(_qfix_items), len(_qfix_subitems), len(_qfix_services))


def enrich_qfix(qfix):
    """Add QFix catalog item, subitem, and service data to a qfix mapping dict.

    Services are looked up by the (clothing_type_id, material_id) pair, matching
    the QFix website behavior where services depend on both item and material.
    """
    _load_qfix_catalog()
    ct_id = qfix.get("qfix_clothing_type_id")
    mat_id = qfix.get("qfix_material_id")

    if ct_id and ct_id in _qfix_items:
        qfix["qfix_item"] = _qfix_items[ct_id]

    if mat_id and mat_id in _qfix_subitems:
        qfix["qfix_subitem"] = _qfix_subitems[mat_id]

    if ct_id and mat_id:
        qfix["qfix_services"] = _qfix_services.get((ct_id, mat_id), [])

    return qfix


# ── Brand routing config ──────────────────────────────────────────────────

BRAND_ROUTES = {
    "kappahl": "KappAhl",
    "ginatricot": "Gina Tricot",
    "eton": "Eton",
    "nudie": "Nudie Jeans",
    "lindex": "Lindex",
}

# Reverse lookup: brand display name -> slug
BRAND_SLUG = {v: k for k, v in BRAND_ROUTES.items()}


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def get_write_db():
    url = DATABASE_WRITE_URL or DATABASE_URL
    conn = psycopg2.connect(url)
    conn.autocommit = True
    return conn


def _get_mapper():
    """Return map_product or map_product_legacy based on ?mapping= query param."""
    if request.args.get("mapping") == "legacy":
        return map_product_legacy
    return map_product


# ── Parameterized brand endpoints ─────────────────────────────────────────

@app.route("/<brand_slug>/product/<product_id>")
def get_brand_product(brand_slug, product_id):
    """Look up a product by brand and ID with QFix mapping.
    ---
    tags:
      - KappAhl
      - Gina Tricot
      - Eton
      - Nudie Jeans
      - Lindex
    parameters:
      - name: brand_slug
        in: path
        type: string
        required: true
        description: "Brand slug (kappahl, ginatricot, eton, nudie, lindex)"
      - name: product_id
        in: path
        type: string
        required: true
        description: Product ID
      - name: X-API-Key
        in: header
        type: string
        required: true
        description: Brand-specific API key
    responses:
      200:
        description: Product data with QFix repair category mapping
      401:
        description: Invalid or missing API key
      404:
        description: Product or brand not found
    """
    auth_error = _check_api_key(brand_slug)
    if auth_error:
        return auth_error

    brand_name = BRAND_ROUTES.get(brand_slug)
    if not brand_name:
        return jsonify({"error": f"Unknown brand: {brand_slug}"}), 404

    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, materials, product_url, description, color, brand, image_url, gtin, article_number, care_text, size, country_of_origin, qfix_clothing_type, qfix_clothing_type_id, qfix_material, qfix_material_id, qfix_url FROM products_unified WHERE brand = %s AND product_id = %s",
            (brand_name, product_id),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)

    # Use persisted mapping as base if available, otherwise compute live
    if product.get("qfix_url"):
        qfix = enrich_qfix({
            "qfix_clothing_type": product["qfix_clothing_type"],
            "qfix_clothing_type_id": product["qfix_clothing_type_id"],
            "qfix_material": product["qfix_material"],
            "qfix_material_id": product["qfix_material_id"],
            "qfix_url": product["qfix_url"],
        })
    else:
        qfix = enrich_qfix(_get_mapper()(product, brand=brand_slug))

    return jsonify({
        brand_slug: product,
        "qfix": qfix,
    })


def _redirect_to_qfix(brand_slug, service_key=None):
    """Shared helper: look up product, map to QFix, redirect with optional service_id."""
    brand_name = BRAND_ROUTES.get(brand_slug)
    if not brand_name:
        return jsonify({"error": f"Unknown brand: {brand_slug}"}), 404

    product_id = request.args.get("productId")
    if not product_id:
        return jsonify({"error": "Missing productId query parameter"}), 400

    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, materials, brand, article_number, qfix_clothing_type, qfix_clothing_type_id, qfix_material, qfix_material_id, qfix_url FROM products_unified WHERE brand = %s AND product_id = %s",
            (brand_name, product_id),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)

    # Use persisted mapping if available, otherwise fall back to live mapping
    if product.get("qfix_url"):
        qfix = enrich_qfix({
            "qfix_clothing_type": product["qfix_clothing_type"],
            "qfix_clothing_type_id": product["qfix_clothing_type_id"],
            "qfix_material": product["qfix_material"],
            "qfix_material_id": product["qfix_material_id"],
            "qfix_url": product["qfix_url"],
        })
    else:
        qfix = enrich_qfix(_get_mapper()(product, brand=brand_slug))

    qfix_url = qfix.get("qfix_url")
    if not qfix_url:
        return jsonify({"error": f"No repair mapping available for product {product_id}"}), 404

    if service_key:
        services = qfix.get("qfix_services", [])
        for svc in services:
            if svc.get("slug") and service_key in svc["slug"]:
                qfix_url += ("&" if "?" in qfix_url else "?") + f"service_id={svc['id']}"
                break

    return redirect(qfix_url, code=302)


@app.route("/<brand_slug>/repair/")
def redirect_to_repair(brand_slug):
    """Redirect to QFix repair booking page.

    Usage: /<brand>/repair/?productId=534008
    ---
    tags:
      - Redirect
    parameters:
      - name: brand_slug
        in: path
        type: string
        required: true
      - name: productId
        in: query
        type: string
        required: true
    responses:
      302:
        description: Redirect to QFix booking page with service_id for repair
      404:
        description: Product not found or no repair available
    """
    return _redirect_to_qfix(brand_slug, service_key="repair")


@app.route("/<brand_slug>/adjustment/")
def redirect_to_adjustment(brand_slug):
    """Redirect to QFix adjustment booking page.

    Usage: /<brand>/adjustment/?productId=534008
    ---
    tags:
      - Redirect
    parameters:
      - name: brand_slug
        in: path
        type: string
        required: true
      - name: productId
        in: query
        type: string
        required: true
    responses:
      302:
        description: Redirect to QFix booking page with service_id for adjustment
      404:
        description: Product not found or no adjustment available
    """
    return _redirect_to_qfix(brand_slug, service_key="adjustment")


@app.route("/<brand_slug>/care/")
def redirect_to_care(brand_slug):
    """Redirect to QFix washing & care booking page.

    Usage: /<brand>/care/?productId=534008
    ---
    tags:
      - Redirect
    parameters:
      - name: brand_slug
        in: path
        type: string
        required: true
      - name: productId
        in: query
        type: string
        required: true
    responses:
      302:
        description: Redirect to QFix booking page with service_id for washing/care
      404:
        description: Product not found or no care service available
    """
    return _redirect_to_qfix(brand_slug, service_key="washing")


@app.route("/<brand_slug>/products")
def list_brand_products(brand_slug):
    """List products for a brand (limit 100).
    ---
    tags:
      - KappAhl
      - Gina Tricot
      - Eton
      - Nudie Jeans
      - Lindex
    parameters:
      - name: brand_slug
        in: path
        type: string
        required: true
        description: "Brand slug (kappahl, ginatricot, eton, nudie, lindex)"
      - name: X-API-Key
        in: header
        type: string
        required: true
        description: Brand-specific API key
    responses:
      200:
        description: Array of products
      401:
        description: Invalid or missing API key
      404:
        description: Unknown brand
    """
    auth_error = _check_api_key(brand_slug)
    if auth_error:
        return auth_error

    brand_name = BRAND_ROUTES.get(brand_slug)
    if not brand_name:
        return jsonify({"error": f"Unknown brand: {brand_slug}"}), 404

    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT product_id, product_name, category, clothing_type, material_composition, materials, description, color, brand, gtin, article_number, care_text, size, country_of_origin FROM products_unified WHERE brand = %s ORDER BY product_id LIMIT 100",
            (brand_name,),
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── Legacy v1 routes (aliases to kappahl) ─────────────────────────────────

@app.route("/product/<product_id>")
def get_product(product_id):
    """Look up a KappAhl product by ID (legacy route).
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
    return get_brand_product("kappahl", product_id)


@app.route("/products")
def list_products():
    """List KappAhl products (legacy route, limit 100).
    ---
    tags:
      - KappAhl
    responses:
      200:
        description: Array of KappAhl products
    """
    return list_brand_products("kappahl")


# ── v2 endpoints (T4V protocol xlsx) ─────────────────────────────────────

@app.route("/v2/upload", methods=["POST"])
@limiter.limit("10 per minute")
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

    conn = get_write_db()
    create_table(conn)
    count = 0
    for prod in products:
        upsert_product(conn, prod)
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin FROM products_unified WHERE gtin = %s",
            (gtin,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"GTIN {gtin} not found"}), 404

    product = dict(row)
    qfix = enrich_qfix(map_product_v2(product))

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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT gtin, article_number, product_name, description, category, size, color, materials, care_text, brand, country_of_origin FROM products_unified WHERE article_number = %s ORDER BY size",
            (article_number,),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": f"Article {article_number} not found"}), 404

    products = [dict(r) for r in rows]
    qfix = enrich_qfix(map_product_v2(products[0]))

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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT gtin, article_number, product_name, category, size, color, brand FROM products_unified WHERE gtin IS NOT NULL ORDER BY article_number, size LIMIT 200"
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── v3 endpoints (legacy Gina Tricot aliases) ─────────────────────────────

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
            "SELECT product_id, product_name, category, clothing_type, material_composition, product_url, description, color, brand FROM products_unified WHERE brand = %s AND product_id = %s",
            ("Gina Tricot", product_id),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = enrich_qfix(_get_mapper()(product, brand="ginatricot"))

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
            "SELECT product_id, product_name, category, clothing_type, material_composition, description, color, brand FROM products_unified WHERE brand = %s ORDER BY product_id LIMIT 200",
            ("Gina Tricot",),
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
            "SELECT product_id, product_name, category, clothing_type, color, brand FROM products_unified WHERE brand = %s AND product_name ILIKE %s ORDER BY product_id LIMIT 50",
            ("Gina Tricot", f"%{q}%"),
        )
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


# ── v4 endpoints (aggregated: enriched data from single table) ────────────

def _merge_product(product):
    """Build merged view from a unified product row that has both scraped and protocol data."""
    import json as _json

    merged = {
        "product_name": product.get("product_name"),
        "brand": product.get("brand"),
        "color": product.get("color"),
        "description_sv": product.get("description"),
        "description_en": product.get("description"),
        "category_scraped": product.get("category"),
        "category_protocol": product.get("category"),
        "clothing_type": product.get("clothing_type"),
        "material_composition": product.get("material_composition"),
        "materials_structured": product.get("materials"),
        "care_text": product.get("care_text"),
        "country_of_origin": product.get("country_of_origin"),
        "product_url": product.get("product_url"),
        "product_id": product.get("product_id"),
        "article_number": product.get("article_number"),
        "source": "merged" if product.get("article_number") else "scraper_only",
    }

    materials_list = None
    raw = product.get("materials")
    if raw and isinstance(raw, str):
        try:
            materials_list = _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            pass

    return merged, materials_list


@app.route("/v4/product/<product_id>")
def v4_get_product(product_id):
    """Get a product with merged scraper + protocol data.
    ---
    tags:
      - Aggregated
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Product ID
    responses:
      200:
        description: Merged product data (source is 'merged' or 'scraper_only')
      404:
        description: Product not found
    """
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT product_id, product_name, category, clothing_type, material_composition,
                      product_url, description, color, brand, image_url, materials, care_text,
                      country_of_origin, article_number,
                      qfix_clothing_type, qfix_clothing_type_id, qfix_material,
                      qfix_material_id, qfix_url
               FROM products_unified WHERE product_id = %s LIMIT 1""",
            (product_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    merged, materials_list = _merge_product(product)

    # Use persisted mapping if available, otherwise compute live
    if product.get("qfix_url"):
        qfix = enrich_qfix({
            "qfix_clothing_type": product["qfix_clothing_type"],
            "qfix_clothing_type_id": product["qfix_clothing_type_id"],
            "qfix_material": product["qfix_material"],
            "qfix_material_id": product["qfix_material_id"],
            "qfix_url": product["qfix_url"],
        })
    else:
        brand_slug = BRAND_SLUG.get(product.get("brand"))
        if product.get("article_number"):
            qfix = enrich_qfix(map_product_v2(product, materials=materials_list))
        else:
            qfix = enrich_qfix(_get_mapper()(product, brand=brand_slug))

    return jsonify({
        "product": merged,
        "qfix": qfix,
    })


@app.route("/v4/products")
def v4_list_products():
    """List aggregated products (limit 200).
    ---
    tags:
      - Aggregated
    responses:
      200:
        description: Array of products with merge status
    """
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT product_id, product_name, category, clothing_type,
                   material_composition, description, color, brand,
                   article_number AS protocol_article,
                   category AS protocol_category,
                   care_text, country_of_origin,
                   CASE WHEN article_number IS NOT NULL THEN 'merged' ELSE 'scraper_only' END AS source
            FROM products_unified
            ORDER BY product_id
            LIMIT 200
        """)
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


@app.route("/v4/product/search")
def v4_search():
    """Search products by name.
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
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT product_id, product_name, category, clothing_type, color, brand,
                   CASE WHEN article_number IS NOT NULL THEN 'merged' ELSE 'scraper_only' END AS source
            FROM products_unified
            WHERE product_name ILIKE %s
            ORDER BY product_id
            LIMIT 50
        """, (f"%{q}%",))
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
@limiter.limit("20 per minute")
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

    known_brands = tuple(BRAND_ROUTES.values())
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT DISTINCT brand, clothing_type, material_composition, category FROM products_unified WHERE clothing_type IS NOT NULL AND brand IN %s ORDER BY brand, clothing_type",
            (known_brands,),
        )
        all_rows = cur.fetchall()

    conn.close()

    # Group by brand
    by_brand = {}
    for row in all_rows:
        brand = row["brand"]
        if brand not in by_brand:
            by_brand[brand] = []
        by_brand[brand].append(row)

    for brand_name, rows in by_brand.items():
        slug = BRAND_SLUG.get(brand_name, brand_name.lower().replace(" ", ""))
        unmapped_types = {}
        unmapped_materials = set()

        for row in rows:
            ct = row["clothing_type"]
            mat = row["material_composition"]
            mapped_type = map_clothing_type(ct, brand=slug)
            if mapped_type is None and ct:
                if ct not in unmapped_types:
                    unmapped_types[ct] = 0
                unmapped_types[ct] += 1
            mapped_mat = map_material(mat, brand=slug)
            if mapped_mat == "Other/Unsure" and mat:
                unmapped_materials.add(mat)

        result[slug] = {
            "unmapped_clothing_types": [
                {"clothing_type": ct, "distinct_products": count}
                for ct, count in sorted(unmapped_types.items())
            ],
            "unmapped_materials": sorted(unmapped_materials),
        }

    result["qfix_valid_clothing_types"] = {name: id for name, id in sorted(QFIX_CLOTHING_TYPE_IDS.items())}
    result["qfix_valid_materials"] = {
        ct_id: {str(mat_id): mat_name for mat_id, mat_name in mats.items()}
        for ct_id, mats in VALID_MATERIAL_IDS.items()
    }

    # Include current brand override state
    result["brand_overrides"] = {
        "clothing_type": {k: v for k, v in BRAND_CLOTHING_TYPE_OVERRIDES.items() if v},
        "keyword_clothing": {k: v for k, v in BRAND_KEYWORD_CLOTHING_OVERRIDES.items() if v},
        "material": {k: v for k, v in BRAND_MATERIAL_OVERRIDES.items() if v},
    }

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


logger = logging.getLogger(__name__)


@app.route("/remap/run", methods=["POST"])
@limiter.limit("5 per minute")
def remap_run():
    """Batch-compute and persist QFix mappings for all (or per-brand) products.

    Runs the mapping engine on every product and writes the 5 QFix columns
    (clothing_type, clothing_type_id, material, material_id, url) to the DB.
    Products are processed in batches of 100 rows per transaction.
    ---
    tags:
      - Mapping
    parameters:
      - name: brand
        in: query
        type: string
        required: false
        description: "Brand slug to limit the run to (e.g. kappahl, ginatricot, eton, nudie, lindex). Omit to process all brands."
      - name: mapping
        in: query
        type: string
        required: false
        enum: [default, legacy]
        description: "Mapping engine to use. Defaults to the current engine."
    responses:
      200:
        description: Summary of mapping run
        schema:
          type: object
          properties:
            total:
              type: integer
              description: Total products processed
            mapped:
              type: integer
              description: Products that received a QFix URL
            unmapped:
              type: integer
              description: Products with no mapping match
            updated:
              type: integer
              description: DB rows updated
      400:
        description: Unknown brand slug
    """
    brand_filter = request.args.get("brand")
    if brand_filter and brand_filter not in BRAND_ROUTES:
        return jsonify({"error": f"Unknown brand: {brand_filter}"}), 400

    # Load products from DB
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if brand_filter:
            brand_name = BRAND_ROUTES[brand_filter]
            cur.execute(
                "SELECT product_id, product_name, category, clothing_type, "
                "material_composition, materials, brand, article_number "
                "FROM products_unified WHERE brand = %s",
                (brand_name,),
            )
        else:
            cur.execute(
                "SELECT product_id, product_name, category, clothing_type, "
                "material_composition, materials, brand, article_number "
                "FROM products_unified"
            )
        rows = cur.fetchall()
    conn.close()

    mapper = _get_mapper()
    total = len(rows)
    mapped = 0
    unmapped = 0
    updated = 0

    write_conn = get_write_db()

    # Process in batches of 100
    write_conn.autocommit = False
    batch_count = 0

    try:
        for row in rows:
            product = dict(row)
            slug = BRAND_SLUG.get(product.get("brand"))
            qfix = mapper(product, brand=slug)

            if qfix.get("qfix_url"):
                mapped += 1
            else:
                unmapped += 1

            update_qfix_mapping(
                write_conn,
                product["brand"],
                product["product_id"],
                qfix,
            )
            batch_count += 1
            updated += 1

            if batch_count >= 100:
                write_conn.commit()
                batch_count = 0

        # Commit remaining
        if batch_count > 0:
            write_conn.commit()
    except Exception:
        write_conn.rollback()
        raise
    finally:
        write_conn.close()

    return jsonify({
        "total": total,
        "mapped": mapped,
        "unmapped": unmapped,
        "updated": updated,
    })


@app.route("/remap/status")
def remap_status():
    """Get per-brand QFix mapping coverage.

    Returns how many products per brand have a persisted QFix URL vs how many are unmapped.
    ---
    tags:
      - Mapping
    responses:
      200:
        description: Array of per-brand mapping counts
        schema:
          type: array
          items:
            type: object
            properties:
              brand:
                type: string
                description: Brand display name
              total:
                type: integer
                description: Total products for this brand
              mapped:
                type: integer
                description: Products with a persisted qfix_url
              unmapped:
                type: integer
                description: Products without a persisted qfix_url
    """
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT brand, COUNT(*) as total,
                   COUNT(qfix_url) as mapped,
                   COUNT(*) - COUNT(qfix_url) as unmapped
            FROM products_unified GROUP BY brand
        """)
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)


REMAP_PROMPT = """You are a mapping assistant for a clothing repair service (QFix). You will be given a list of unmapped {type_label} values from scraped product data. Your job is to map each value to the correct QFix category, or mark it as "skip" if it's not a repairable clothing/textile item.

## Valid QFix target values

{valid_targets}

## Existing mapping patterns (for reference)

{existing_patterns}

## Unmapped values to process

{unmapped_values}

## Instructions

For each unmapped value:
1. Determine if it represents a repairable clothing/textile item
2. If yes, map it to the closest valid QFix target value from the list above
3. If no (e.g. jewelry, sunglasses, posters, books, non-textile materials like metal/rubber), mark as "skip"
4. For clothing_type mappings, decide if the rule should match the exact category string ("exact") or a keyword within product names ("keyword")

Respond with ONLY a JSON object, no other text:
{{
  "suggestions": [
    {{"from": "the unmapped value (lowercased)", "to": "Valid QFix Target", "match_type": "exact|keyword", "reasoning": "brief explanation"}},
    ...
  ],
  "skipped": [
    {{"value": "the unmapped value", "reasoning": "why it's not mappable"}},
    ...
  ]
}}"""


@app.route("/remap")
@limiter.limit("10 per minute")
def remap_suggestions():
    """Use Claude AI to analyze unmapped items and suggest new mapping rules.
    ---
    tags:
      - Mapping
    parameters:
      - name: type
        in: query
        type: string
        enum: [clothing_type, material]
        default: clothing_type
        description: Type of mapping to analyze
      - name: brand
        in: query
        type: string
        description: Filter by brand slug (e.g. "eton", "nudie"). Omit for all brands.
    responses:
      200:
        description: AI-generated mapping suggestions with reasoning
      500:
        description: Claude API error
    """
    mapping_type = request.args.get("type", "clothing_type")
    brand_filter = request.args.get("brand")

    if mapping_type not in ("clothing_type", "material"):
        return jsonify({"error": "type must be 'clothing_type' or 'material'"}), 400

    # Gather unmapped items (reuse /unmapped logic)
    known_brands = tuple(BRAND_ROUTES.values())
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT DISTINCT brand, clothing_type, material_composition, category "
            "FROM products_unified WHERE clothing_type IS NOT NULL "
            "AND brand IN %s ORDER BY brand, clothing_type",
            (known_brands,),
        )
        all_rows = cur.fetchall()
    conn.close()

    unmapped_items = {}  # value -> {"count": N, "brands": set, "samples": []}

    for row in all_rows:
        brand_name = row["brand"]
        slug = BRAND_SLUG.get(brand_name, brand_name.lower().replace(" ", ""))
        if brand_filter and slug != brand_filter:
            continue

        if mapping_type == "clothing_type":
            val = row["clothing_type"]
            mapped = map_clothing_type(val)
            if mapped is None and val:
                key = val
                if key not in unmapped_items:
                    unmapped_items[key] = {"count": 0, "brands": set()}
                unmapped_items[key]["count"] += 1
                unmapped_items[key]["brands"].add(slug)
        else:
            val = row["material_composition"]
            mapped = map_material(val)
            if mapped == "Other/Unsure" and val:
                key = val
                if key not in unmapped_items:
                    unmapped_items[key] = {"count": 0, "brands": set()}
                unmapped_items[key]["count"] += 1
                unmapped_items[key]["brands"].add(slug)

    if not unmapped_items:
        return jsonify({"suggestions": [], "skipped": [], "message": "Nothing unmapped!"})

    # Build prompt context
    if mapping_type == "clothing_type":
        valid_targets = ", ".join(sorted(QFIX_CLOTHING_TYPE_IDS.keys()))
        sample_patterns = list(CLOTHING_TYPE_MAP.items())[:20]
        existing_patterns = "\n".join(f'  "{k}" -> "{v}"' for k, v in sample_patterns)
        keyword_samples = _KEYWORD_CLOTHING_MAP[:15]
        existing_patterns += "\n\nKeyword rules (match anywhere in string):\n"
        existing_patterns += "\n".join(f'  keyword "{k}" -> "{v}"' for k, v in keyword_samples)
        type_label = "clothing type"
    else:
        valid_targets = "Standard textile, Linen/Wool, Cashmere, Silk, Leather/Suede, Down, Fur, Other/Unsure"
        sample_patterns = list(MATERIAL_MAP.items())[:20]
        existing_patterns = "\n".join(f'  "{k}" -> "{v}"' for k, v in sample_patterns if v)
        type_label = "material"

    unmapped_lines = []
    for val, info in sorted(unmapped_items.items(), key=lambda x: -x[1]["count"]):
        brands = ", ".join(sorted(info["brands"]))
        unmapped_lines.append(f'  - "{val}" ({info["count"]} products, brands: {brands})')

    prompt = REMAP_PROMPT.format(
        type_label=type_label,
        valid_targets=valid_targets,
        existing_patterns=existing_patterns,
        unmapped_values="\n".join(unmapped_lines),
    )

    # Call Claude API
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()

        # Parse JSON (handle markdown code blocks)
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        # Enrich suggestions with product counts
        for s in result.get("suggestions", []):
            from_val = s.get("from", "")
            # Try case-insensitive match
            for orig_val, info in unmapped_items.items():
                if orig_val.lower() == from_val.lower():
                    s["products_affected"] = info["count"]
                    s["brands"] = sorted(info["brands"])
                    break

        return jsonify(result)

    except json.JSONDecodeError:
        logger.error("Failed to parse remap response: %s", response_text)
        return jsonify({"error": "Failed to parse AI response", "raw": response_text}), 500
    except Exception as e:
        logger.error("Remap API error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/remap/apply", methods=["POST"])
@limiter.limit("10 per minute")
def remap_apply():
    """Apply AI-suggested mapping rules (in-memory, resets on redeploy).
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
            - suggestions
          properties:
            suggestions:
              type: array
              items:
                type: object
                properties:
                  from:
                    type: string
                  to:
                    type: string
                  rule_type:
                    type: string
                    enum: [clothing_type, material]
                  match_type:
                    type: string
                    enum: [exact, keyword]
    responses:
      200:
        description: Mappings applied successfully
      400:
        description: Invalid input
    """
    data = request.get_json()
    if not data or "suggestions" not in data:
        return jsonify({"error": "JSON body with 'suggestions' array required"}), 400

    brand = data.get("brand") or request.args.get("brand")
    if brand and brand not in BRAND_ROUTES:
        return jsonify({"error": f"Unknown brand: {brand}"}), 400

    valid_materials = {"Standard textile", "Linen/Wool", "Cashmere", "Silk",
                       "Leather/Suede", "Down", "Fur", "Other/Unsure"}
    applied = []
    errors = []

    for s in data["suggestions"]:
        from_val = s.get("from", "").strip().lower()
        to_val = s.get("to", "").strip()
        rule_type = s.get("rule_type", "clothing_type")
        match_type = s.get("match_type", "exact")

        if not from_val or not to_val:
            errors.append({"from": from_val, "error": "Missing from or to"})
            continue

        if rule_type == "clothing_type":
            if to_val not in QFIX_CLOTHING_TYPE_IDS:
                errors.append({"from": from_val, "error": f"Invalid QFix type: '{to_val}'"})
                continue
            if brand:
                if match_type == "keyword":
                    BRAND_KEYWORD_CLOTHING_OVERRIDES.setdefault(brand, []).append((from_val, to_val))
                    applied.append({"from": from_val, "to": to_val, "type": "brand_keyword_rule", "brand": brand})
                else:
                    BRAND_CLOTHING_TYPE_OVERRIDES.setdefault(brand, {})[from_val] = to_val
                    applied.append({"from": from_val, "to": to_val, "type": "brand_exact_rule", "brand": brand})
            else:
                if match_type == "keyword":
                    _KEYWORD_CLOTHING_MAP.append((from_val, to_val))
                    applied.append({"from": from_val, "to": to_val, "type": "keyword_rule"})
                else:
                    CLOTHING_TYPE_MAP[from_val] = to_val
                    applied.append({"from": from_val, "to": to_val, "type": "exact_rule"})

        elif rule_type == "material":
            if to_val not in valid_materials:
                errors.append({"from": from_val, "error": f"Invalid material: '{to_val}'"})
                continue
            if brand:
                BRAND_MATERIAL_OVERRIDES.setdefault(brand, {})[from_val] = to_val
                applied.append({"from": from_val, "to": to_val, "type": "brand_material_rule", "brand": brand})
            else:
                MATERIAL_MAP[from_val] = to_val
                applied.append({"from": from_val, "to": to_val, "type": "material_rule"})

        else:
            errors.append({"from": from_val, "error": f"Invalid rule_type: '{rule_type}'"})

    return jsonify({
        "applied": applied,
        "applied_count": len(applied),
        "errors": errors,
    })


# --- Health check ---

@app.route("/health")
@limiter.exempt
def health():
    """Health check endpoint.
    ---
    tags:
      - Health
    responses:
      200:
        description: Service is healthy
      500:
        description: Database unreachable
    """
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


# --- QFix Widget Demo ---

WIDGET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget")


@app.route("/widget.js")
def widget_js():
    return send_from_directory(WIDGET_DIR, "widget.js", mimetype="application/javascript")


@app.route("/demo")
@app.route("/demo/")
def widget_demo():
    return send_from_directory(os.path.join(WIDGET_DIR, "demo"), "index.html")


# --- Mapping Documentation & Verification ---

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


@app.route("/docs")
@app.route("/docs/")
def docs_page():
    return send_from_directory(DOCS_DIR, "index.html")


@app.route("/docs/verify/<product_id>")
def docs_verify(product_id):
    """Verify the QFix mapping for a product, showing each step.
    ---
    tags:
      - Mapping
    parameters:
      - name: product_id
        in: path
        type: string
        required: true
        description: Product ID to verify
    responses:
      200:
        description: Step-by-step mapping breakdown with service URLs
      404:
        description: Product not found
    """
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT product_id, product_name, brand, category, clothing_type,
                      material_composition, materials, article_number,
                      qfix_clothing_type, qfix_clothing_type_id, qfix_material,
                      qfix_material_id, qfix_url
               FROM products_unified WHERE product_id = %s LIMIT 1""",
            (product_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    brand_slug = BRAND_SLUG.get(product.get("brand"))

    # Run live mapping to show each step
    ct_input = product.get("clothing_type")
    mat_input = product.get("material_composition")
    cat_input = product.get("category")

    ct_result = map_clothing_type(ct_input, brand=brand_slug)
    mat_result = map_material(mat_input, brand=brand_slug)
    subcat = map_category(cat_input)

    ct_id = _resolve_clothing_type_id(ct_result, subcat) if ct_result else None
    mat_id = _resolve_material_id(ct_id, mat_result) if ct_id and mat_result else None

    live_url = None
    if ct_id and mat_id:
        live_url = f"https://kappahl.dev.qfixr.me/sv/?category_id={ct_id}&material_id={mat_id}"

    # Check persisted vs live
    persisted_url = product.get("qfix_url")
    final_url = persisted_url or live_url

    # Build enriched qfix with services
    qfix_data = {
        "qfix_clothing_type": ct_result,
        "qfix_clothing_type_id": ct_id,
        "qfix_material": mat_result,
        "qfix_material_id": mat_id,
        "qfix_url": final_url,
    }
    enriched = enrich_qfix(qfix_data)

    # Build service URLs
    services = []
    for svc_cat in enriched.get("qfix_services", []):
        slug = svc_cat.get("slug", "")
        svc_url = None
        if final_url and svc_cat.get("id"):
            sep = "&" if "?" in final_url else "?"
            svc_url = f"{final_url}{sep}service_id={svc_cat['id']}"
        services.append({
            "name": svc_cat.get("name"),
            "slug": slug,
            "service_id": svc_cat.get("id"),
            "url": svc_url,
        })

    return jsonify({
        "product": {
            "product_id": product["product_id"],
            "product_name": product.get("product_name"),
            "brand": product.get("brand"),
            "category": cat_input,
            "clothing_type": ct_input,
            "material_composition": mat_input,
        },
        "mapping": {
            "clothing_type_input": ct_input,
            "clothing_type_result": ct_result,
            "clothing_type_id": ct_id,
            "material_input": mat_input,
            "material_result": mat_result,
            "material_id": mat_id,
            "subcategory": subcat,
            "qfix_url": final_url,
            "persisted": persisted_url is not None,
            "live_url": live_url,
        },
        "services": services,
    })


@app.route("/docs/mappings")
def docs_mappings():
    """Return the full mapping tables for the documentation page."""
    clothing = {k: v for k, v in sorted(CLOTHING_TYPE_MAP.items()) if v is not None}
    materials = {k: v for k, v in sorted(MATERIAL_MAP.items()) if v is not None}
    return jsonify({
        "clothing_type_map": clothing,
        "material_map": materials,
    })


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    import database
    database.DATABASE_URL = os.environ.get("DATABASE_URL")
    app.run(debug=True, port=8000)
