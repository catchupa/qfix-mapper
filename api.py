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
from database import (create_table, upsert_product, update_qfix_mapping,
                      upsert_action_ranking, get_action_ranking,
                      DATABASE_URL, DATABASE_WRITE_URL)
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


# --- DB connections with retry and timeout ---

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
                _time.sleep(delay * (attempt + 1))
    raise last_err


def get_db():
    return _connect_with_retry(DATABASE_URL)


def get_write_db():
    url = DATABASE_WRITE_URL or DATABASE_URL
    return _connect_with_retry(url)


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
            "SELECT product_id, product_name, description, category, clothing_type, material_composition, materials, brand, article_number, qfix_clothing_type, qfix_clothing_type_id, qfix_material, qfix_material_id, qfix_url FROM products_unified WHERE brand = %s AND product_id = %s",
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

        # Add top-ranked action IDs as variants_id
        ct_id = qfix.get("qfix_clothing_type_id")
        mat_id = qfix.get("qfix_material_id")
        if ct_id and mat_id:
            ranking_key_map = {"repair": "repair", "adjustment": "adjustment", "washing": "care", "customize": "other"}
            ranking_key = ranking_key_map.get(service_key)
            if ranking_key:
                ranking_conn = get_db()
                top_actions = get_action_ranking(ranking_conn, ct_id, mat_id) or {}
                ranking_conn.close()

                # Apply keyword-based injection for this product
                product_text = " ".join(filter(None, [
                    product.get("product_name", ""),
                    product.get("description", ""),
                    product.get("clothing_type", ""),
                ])).lower()
                if product_text and qfix.get("qfix_services"):
                    top_actions = _inject_keyword_actions(
                        top_actions, product_text, qfix["qfix_services"])

                actions = top_actions.get(ranking_key, [])
                if actions:
                    ids = ",".join(str(a["id"]) for a in actions)
                    qfix_url += ("&" if "?" in qfix_url else "?") + f"variants_id={ids}"

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

    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", 0, type=int)

    # Load products from DB
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        base_query = (
            "SELECT product_id, product_name, category, clothing_type, "
            "material_composition, materials, brand, article_number "
            "FROM products_unified"
        )
        params = []
        if brand_filter:
            brand_name = BRAND_ROUTES[brand_filter]
            base_query += " WHERE brand = %s"
            params.append(brand_name)
        base_query += " ORDER BY id"
        if limit:
            base_query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
        cur.execute(base_query, params)
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

    # Ensure QFix catalog is loaded for service ID resolution
    _load_qfix_catalog()

    # Slug-to-service-category mapping
    _SERVICE_SLUG_MAP = {
        "repair": "qfix_url_repair",
        "adjustment": "qfix_url_adjustment",
        "washing": "qfix_url_care",
        "customize": "qfix_url_other",
    }

    try:
        for row in rows:
            product = dict(row)
            slug = BRAND_SLUG.get(product.get("brand"))
            qfix = mapper(product, brand=slug)

            if qfix.get("qfix_url"):
                mapped += 1
            else:
                unmapped += 1

            # Resolve service URLs
            base_url = qfix.get("qfix_url")
            ct_id = qfix.get("qfix_clothing_type_id")
            mat_id = qfix.get("qfix_material_id")
            if base_url and ct_id and mat_id:
                service_cats = _qfix_services.get((ct_id, mat_id), [])
                for svc_cat in service_cats:
                    svc_slug = svc_cat.get("slug", "")
                    svc_id = svc_cat.get("id")
                    if svc_id:
                        sep = "&" if "?" in base_url else "?"
                        svc_url = f"{base_url}{sep}service_id={svc_id}"
                        for key, col in _SERVICE_SLUG_MAP.items():
                            if key in svc_slug:
                                qfix[col] = svc_url
                                break

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


RANK_ACTIONS_PROMPT = """You are a clothing repair service expert. For a **{clothing_type}** made of **{material}**, rank the following {service_name} actions by how likely a typical customer would need them.

CRITICAL: Only include actions that are PHYSICALLY POSSIBLE for this specific garment type.
- Do NOT include leg/thigh actions (Tapering legs, Expand thigh, Shorten legs, Lengthen legs) for items without legs (caps, hats, gloves, scarves, bikinis, underwear, bags, belts, etc.)
- Do NOT include sleeve actions (Shorten sleeves, Lengthen sleeves, Narrow shoulder area) for items without sleeves (caps, hats, gloves, scarves, bikinis, underwear, swimming trunks, skirts, bags, belts, etc.)
- Do NOT include shoe actions (Replace heel, Replace sole, Resole) for non-footwear items.
- Think carefully: does a {clothing_type} actually have the body part this action refers to?

Available actions:
{actions_list}

Return ONLY a JSON array of the top 10 most relevant action names (as strings), ordered by likelihood. If fewer than 10 actions are physically applicable, return fewer. Example: ["Repair seam", "Replace button", "Repair tear"]"""

# Keyword → action injection: Swedish/English keywords in product text → actions to boost
# Each entry: list of keywords (any match triggers), action names to inject, which ranking category
MAX_INJECTED_PER_RULE = 2  # Max actions injected per keyword rule

KEYWORD_ACTION_RULES = [
    {
        "keywords": ["dragkedja", "zipper", "blixtlås", "zip"],
        "actions": [
            {"name": "Replace zipper", "default": True},
            {"name": "Replace main zipper", "sub_keywords": ["jacka", "jacket", "coat", "kappa", "rock"]},
            {"name": "Replace zipper slider", "sub_keywords": ["slider", "dragare", "rits"]},
        ],
        "category": "repair",
    },
    {
        "keywords": ["knapp", "knappar", "button", "buttons"],
        "actions": [
            {"name": "Replace button", "default": True},
            {"name": "Replace snap button", "sub_keywords": ["tryck", "snap", "press"]},
            {"name": "Replace jeans button", "sub_keywords": ["jeans", "denim", "jean"]},
            {"name": "Place new button"},
            {"name": "Exchange button"},
        ],
        "category": "repair",
    },
    {
        "keywords": ["spänne", "buckle"],
        "actions": [{"name": "Replace buckle", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["foder", "lining", "fodrad"],
        "actions": [
            {"name": "Replace lining", "default": True},
            {"name": "Attach new inner lining"},
        ],
        "category": "repair",
    },
    {
        "keywords": ["resår", "elastic", "elastisk"],
        "actions": [{"name": "Replace elastic", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["kardborre", "velcro"],
        "actions": [{"name": "Replace velcro", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["reflex", "reflexer", "reflective"],
        "actions": [{"name": "Replace reflectors", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["läder", "leather", "skinn", "mocka", "suede", "nubuck"],
        "actions": [{"name": "Clean and condition", "default": True}],
        "category": "care",
    },
    {
        "keywords": ["dun", "dunfyllning", "down filled", "down jacket"],
        "actions": [{"name": "Dry cleaning", "default": True}],
        "category": "care",
    },
    {
        "keywords": ["impregnera", "waterproof", "vattentät", "gore-tex", "shell"],
        "actions": [{"name": "Waterproofing", "default": True}],
        "category": "care",
    },
]

# Keyword → action exclusion: remove irrelevant actions based on product text
# Each entry: keywords to match in product text, action names to exclude, category
KEYWORD_EXCLUSION_RULES = [
    {
        "keywords": ["väst", "vest", "gilet", "bodywarmer"],
        "exclude_actions": ["Shorten sleeves", "Lengthen sleeves"],
        "category": "adjustment",
    },
    {
        "keywords": ["väst", "vest", "gilet", "bodywarmer"],
        "exclude_actions": ["Tapering legs", "Shorten legs", "Lengthen legs"],
        "category": "adjustment",
    },
    {
        "keywords": ["linne", "singlet", "tank top", "ärmlös", "sleeveless", "bandeau", "tubtopp"],
        "exclude_actions": ["Shorten sleeves", "Lengthen sleeves"],
        "category": "adjustment",
    },
    {
        "keywords": ["shorts"],
        "exclude_actions": ["Tapering legs"],
        "category": "adjustment",
    },
    {
        "keywords": ["kjol", "skirt"],
        "exclude_actions": ["Shorten sleeves", "Lengthen sleeves", "Tapering legs"],
        "category": "adjustment",
    },
    {
        "keywords": ["badshorts", "swim shorts", "badbyxor"],
        "exclude_actions": ["Replace zipper", "Replace main zipper", "Replace zipper slider"],
        "category": "repair",
    },
    {
        "keywords": ["badshorts", "swim shorts", "badbyxor"],
        "exclude_actions": ["Narrow shoulder area", "Shorten sleeves", "Lengthen sleeves", "Shorten length"],
        "category": "adjustment",
    },
    {
        "keywords": ["bikini", "baddräkt", "swimsuit", "badedrakt"],
        "exclude_actions": ["Shorten sleeves", "Lengthen sleeves", "Tapering legs", "Shorten length"],
        "category": "adjustment",
    },
    {
        "keywords": ["strumpor", "socks", "sockor", "strumpa"],
        "exclude_actions": ["Take in waist", "Expand waist", "Take in sides", "Shorten length", "Take in the back",
                            "Narrow shoulder area", "Shorten sleeves", "Lengthen sleeves", "Tapering legs"],
        "category": "adjustment",
    },
    {
        "keywords": ["strumpbyxa", "strumpbyxor", "tights", "pantyhose"],
        "exclude_actions": ["Take in waist", "Expand waist", "Take in sides", "Shorten length", "Take in the back",
                            "Narrow shoulder area", "Shorten sleeves", "Lengthen sleeves", "Tapering legs"],
        "category": "adjustment",
    },
    {
        "keywords": ["poncho"],
        "exclude_actions": ["Shorten sleeves", "Lengthen sleeves"],
        "category": "adjustment",
    },
    {
        "keywords": ["cape"],
        "exclude_actions": ["Shorten sleeves", "Lengthen sleeves"],
        "category": "adjustment",
    },
    {
        "keywords": ["leggings"],
        "exclude_actions": ["Tapering legs"],
        "category": "adjustment",
    },
    {
        "keywords": ["leggings"],
        "exclude_actions": ["Replace main zipper", "Replace zipper", "Replace zipper slider"],
        "category": "repair",
    },
    {
        "keywords": ["bandeau", "tubtopp", "tube top", "strapless"],
        "exclude_actions": ["Narrow shoulder area"],
        "category": "adjustment",
    },
    {
        "keywords": ["träningstights", "traningstights", "cykelbyxa", "cykelbyxor", "cycling shorts"],
        "exclude_actions": ["Shorten sleeves", "Lengthen sleeves", "Narrow shoulder area"],
        "category": "adjustment",
    },
    {
        "keywords": ["träningstights", "traningstights", "cykelbyxa", "cykelbyxor", "cycling shorts"],
        "exclude_actions": ["Replace main zipper", "Replace zipper", "Replace zipper slider"],
        "category": "repair",
    },
]


def _inject_keyword_actions(top_actions, product_text, qfix_services):
    """Inject/exclude actions in top_actions based on keywords found in product text."""
    if not product_text:
        return top_actions

    # Build set of action names to exclude per category
    excluded = {}  # category_key -> set of action names
    for rule in KEYWORD_EXCLUSION_RULES:
        if any(kw in product_text for kw in rule["keywords"]):
            cat = rule["category"]
            if cat not in excluded:
                excluded[cat] = set()
            excluded[cat].update(rule["exclude_actions"])

    # Build a lookup: action name -> {id, name, price} from all services
    all_actions = {}  # name -> list of {id, name, price, category_key}
    service_slug_to_key = {
        "repair": "repair", "adjustment": "adjustment",
        "washing": "care", "customize": "other",
    }
    for svc_cat in qfix_services:
        svc_slug = svc_cat.get("slug", "")
        cat_key = None
        for slug_part, key in service_slug_to_key.items():
            if slug_part in svc_slug:
                cat_key = key
                break
        if not cat_key:
            continue
        for s in svc_cat.get("services", []):
            name = s["name"]
            if name not in all_actions:
                all_actions[name] = []
            all_actions[name].append({
                "id": s["id"], "name": name,
                "price": s.get("price"), "category_key": cat_key,
            })

    # Check each keyword rule — inject at most MAX_INJECTED_PER_RULE actions
    injected = {}  # category_key -> list of actions to inject
    for rule in KEYWORD_ACTION_RULES:
        if any(kw in product_text for kw in rule["keywords"]):
            cat = rule["category"]
            if cat not in injected:
                injected[cat] = []

            # First pass: collect actions whose sub_keywords match the product
            sub_matched = []
            default_action = None
            for action_def in rule["actions"]:
                action_name = action_def["name"]
                if action_name not in all_actions:
                    continue
                variants = [a for a in all_actions[action_name] if a["category_key"] == cat]
                if not variants:
                    variants = all_actions[action_name]
                best = min(variants, key=lambda a: a["price"] or 9999)
                entry = {"id": best["id"], "name": best["name"], "price": best["price"]}

                if action_def.get("sub_keywords") and any(sk in product_text for sk in action_def["sub_keywords"]):
                    sub_matched.append(entry)
                elif action_def.get("default"):
                    default_action = entry

            # Build final list: sub-keyword matches first, then default, capped at MAX_INJECTED_PER_RULE
            selected = list(sub_matched)
            if default_action and len(selected) < MAX_INJECTED_PER_RULE:
                # Add default only if no sub-keyword match already covers it
                if not any(a["name"] == default_action["name"] for a in selected):
                    selected.append(default_action)
            injected[cat].extend(selected[:MAX_INJECTED_PER_RULE])

    if not injected and not excluded:
        # Still trim to 5 (DB may store up to 10)
        return {cat: actions[:5] for cat, actions in top_actions.items()}

    result = dict(top_actions)

    # Step 1: Apply exclusion rules first (on the full pool of up to 10 actions)
    # This allows backfilling from positions 6-10 when earlier actions are excluded
    if excluded:
        for cat, names_to_remove in excluded.items():
            if cat in result:
                result[cat] = [a for a in result[cat] if a["name"] not in names_to_remove]

    # Step 2: Score-based merge with keyword-injected actions, pick best 5
    if injected:
        ai_scores = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        kw_scores = [7, 5, 3, 1, 1]

        for cat, new_actions in injected.items():
            existing = list(result.get(cat, []))

            scored = []
            seen_ids = set()
            seen_names = set()
            for i, a in enumerate(existing):
                score = ai_scores[i] if i < len(ai_scores) else 1
                scored.append((score, a))
                seen_ids.add(a["id"])
                seen_names.add(a["name"])

            kw_idx = 0
            for a in new_actions:
                if a["id"] not in seen_ids and a["name"] not in seen_names:
                    score = kw_scores[kw_idx] if kw_idx < len(kw_scores) else 1
                    scored.append((score, a))
                    seen_ids.add(a["id"])
                    seen_names.add(a["name"])
                    kw_idx += 1

            scored.sort(key=lambda x: x[0], reverse=True)
            result[cat] = [a for _, a in scored[:5]]
    else:
        # No injection — just trim to 5 after exclusions
        result = {cat: actions[:5] for cat, actions in result.items()}

    return result


@app.route("/remap/rank-actions", methods=["POST"])
@limiter.limit("5 per minute")
def remap_rank_actions():
    """Use AI to rank the top 5 most relevant service actions per clothing type.

    Iterates all unique (clothing_type_id, material_id) combos in the QFix catalog
    and uses Claude to select the 5 most relevant actions per service category.
    Results are persisted in the qfix_action_rankings table.
    ---
    tags:
      - Mapping
    responses:
      200:
        description: Ranking results
        schema:
          type: object
          properties:
            total_combos:
              type: integer
            ranked:
              type: integer
            errors:
              type: integer
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

    _load_qfix_catalog()

    if not _qfix_services:
        return jsonify({"error": "QFix catalog not loaded"}), 500

    ai_client = anthropic.Anthropic(api_key=api_key)

    # Optional: force re-rank specific clothing type IDs or all
    force_ct_ids = None
    body = request.get_json(silent=True) or {}
    force_all = body.get("force_all", False)
    if body.get("force_clothing_type_ids"):
        force_ct_ids = set(body["force_clothing_type_ids"])

    # Load already-ranked combos to skip them (unless forced)
    read_conn = get_db()
    existing = set()
    if not force_all:
        with read_conn.cursor() as cur:
            cur.execute("SELECT clothing_type_id, material_id FROM qfix_action_rankings")
            for row in cur.fetchall():
                if force_ct_ids and row[0] in force_ct_ids:
                    continue  # Don't skip — re-rank these
                existing.add((row[0], row[1]))
    read_conn.close()

    total = len(_qfix_services)
    skipped = len(existing)
    ranked = 0
    errors = 0

    service_slug_to_key = {
        "repair": "repair",
        "adjustment": "adjustment",
        "washing": "care",
        "customize": "other",
    }

    for (ct_id, mat_id), svc_cats in _qfix_services.items():
        if (ct_id, mat_id) in existing:
            continue

        ct_name = _qfix_items.get(ct_id, {}).get("name", f"ID {ct_id}")
        mat_name = _qfix_subitems.get(mat_id, {}).get("name", f"ID {mat_id}")

        rankings = {}

        for svc_cat in svc_cats:
            svc_slug = svc_cat.get("slug", "")
            svc_name = svc_cat.get("name", "")
            services = svc_cat.get("services", [])

            # Determine the key for this service category
            ranking_key = None
            for slug_part, key in service_slug_to_key.items():
                if slug_part in svc_slug:
                    ranking_key = key
                    break
            if not ranking_key:
                continue

            if not services:
                rankings[ranking_key] = []
                continue

            # If 5 or fewer actions, no need to rank
            if len(services) <= 5:
                rankings[ranking_key] = [
                    {"id": s["id"], "name": s["name"], "price": s.get("price")}
                    for s in services
                ]
                continue

            # Build action list for Claude
            action_names = list({s["name"] for s in services})
            actions_list = "\n".join(f"- {name}" for name in sorted(action_names))

            prompt = RANK_ACTIONS_PROMPT.format(
                clothing_type=ct_name,
                material=mat_name,
                service_name=svc_name,
                actions_list=actions_list,
            )

            try:
                message = ai_client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=256,
                    messages=[{"role": "user", "content": prompt}],
                )
                response_text = message.content[0].text.strip()

                # Parse JSON (handle markdown code blocks)
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    response_text = "\n".join(lines[1:-1])

                top_names = json.loads(response_text)

                # Handle empty array (Claude says no actions apply)
                if not top_names:
                    rankings[ranking_key] = []
                    continue

                # Match names back to service objects (keep first match for dupes)
                top_actions = []
                seen_names = set()
                for name in top_names:
                    if name in seen_names:
                        continue
                    for s in services:
                        if s["name"] == name and s["id"] not in {a["id"] for a in top_actions}:
                            top_actions.append({
                                "id": s["id"],
                                "name": s["name"],
                                "price": s.get("price"),
                            })
                            seen_names.add(name)
                            break

                rankings[ranking_key] = top_actions[:10]

            except json.JSONDecodeError:
                # Claude likely returned text like "None of these apply" — treat as empty
                logger.info("No applicable actions for ct=%s mat=%s svc=%s (non-JSON response)",
                           ct_id, mat_id, svc_name)
                rankings[ranking_key] = []
            except Exception as e:
                logger.warning("Failed to rank actions for ct=%s mat=%s svc=%s: %s",
                              ct_id, mat_id, svc_name, e)
                rankings[ranking_key] = []
                errors += 1

        # Use a fresh connection for each persist to avoid timeout
        try:
            wc = get_write_db()
            upsert_action_ranking(wc, ct_id, mat_id, rankings)
            wc.close()
            ranked += 1
            logger.info("Ranked ct=%s (%s) mat=%s (%s): %d categories",
                       ct_id, ct_name, mat_id, mat_name,
                       sum(1 for v in rankings.values() if v))
        except Exception as e:
            logger.error("Failed to persist ranking for ct=%s mat=%s: %s", ct_id, mat_id, e)
            errors += 1

    return jsonify({
        "total_combos": total,
        "already_ranked": skipped,
        "newly_ranked": ranked,
        "errors": errors,
    })


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
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        # Return 200 with degraded status to avoid Fly killing the app
        # during transient DB issues — the app itself is still running
        logger.warning("Health check DB probe failed: %s", e)
        return jsonify({"status": "degraded", "detail": str(e)})


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
            """SELECT product_id, product_name, description, brand, category, clothing_type,
                      material_composition, materials, article_number,
                      qfix_clothing_type, qfix_clothing_type_id, qfix_material,
                      qfix_material_id, qfix_url,
                      qfix_url_repair, qfix_url_adjustment, qfix_url_care, qfix_url_other
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

    # Persisted service URLs from DB
    persisted_service_urls = {
        "repair": product.get("qfix_url_repair"),
        "adjustment": product.get("qfix_url_adjustment"),
        "care": product.get("qfix_url_care"),
        "other": product.get("qfix_url_other"),
    }

    # Top ranked actions from DB (or fallback to first 5 from catalog)
    top_actions = {}
    if ct_id and mat_id:
        ranking_conn = get_db()
        top_actions = get_action_ranking(ranking_conn, ct_id, mat_id) or {}
        ranking_conn.close()

    # Fallback: if no rankings persisted, use first 5 unique per service category
    if not top_actions and enriched.get("qfix_services"):
        service_slug_to_key = {
            "repair": "repair", "adjustment": "adjustment",
            "washing": "care", "customize": "other",
        }
        for svc_cat in enriched["qfix_services"]:
            svc_slug = svc_cat.get("slug", "")
            for slug_part, key in service_slug_to_key.items():
                if slug_part in svc_slug:
                    seen = set()
                    actions = []
                    for s in svc_cat.get("services", []):
                        if s["name"] not in seen:
                            actions.append({"id": s["id"], "name": s["name"], "price": s.get("price")})
                            seen.add(s["name"])
                        if len(actions) >= 5:
                            break
                    top_actions[key] = actions
                    break

    # Keyword-based action injection: boost relevant actions based on product text
    if top_actions and enriched.get("qfix_services"):
        product_text = " ".join(filter(None, [
            product.get("product_name", ""),
            product.get("description", ""),
            product.get("clothing_type", ""),
        ])).lower()

        top_actions = _inject_keyword_actions(top_actions, product_text, enriched["qfix_services"])

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
        "persisted_service_urls": persisted_service_urls,
        "top_actions": top_actions,
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


@app.route("/docs/rankings")
def docs_rankings():
    """Return all AI-ranked top actions grouped by clothing type and material."""
    _load_qfix_catalog()
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT clothing_type_id, material_id, rankings FROM qfix_action_rankings ORDER BY clothing_type_id, material_id")
        rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        ct_id = row["clothing_type_id"]
        mat_id = row["material_id"]
        ct_name = _qfix_items.get(ct_id, {}).get("name", f"Unknown ({ct_id})")
        mat_name = _qfix_subitems.get(mat_id, {}).get("name", f"Unknown ({mat_id})")
        rankings = row["rankings"]
        if isinstance(rankings, str):
            rankings = json.loads(rankings)
        results.append({
            "clothing_type_id": ct_id,
            "clothing_type_name": ct_name,
            "material_id": mat_id,
            "material_name": mat_name,
            "rankings": rankings,
        })

    return jsonify(results)


@app.route("/docs/missing-services")
def docs_missing_services():
    """Return QFix clothing types that have no service actions defined."""
    _load_qfix_catalog()

    missing = []
    for (ct_id, mat_id), svc_cats in _qfix_services.items():
        total_actions = sum(len(cat.get("services", [])) for cat in svc_cats)
        if total_actions == 0:
            ct_info = _qfix_items.get(ct_id, {})
            mat_info = _qfix_subitems.get(mat_id, {})
            parent = ct_info.get("parent", {})
            missing.append({
                "clothing_type_id": ct_id,
                "clothing_type_name": ct_info.get("name", f"Unknown ({ct_id})"),
                "parent_category": parent.get("name", "Unknown"),
                "material_id": mat_id,
                "material_name": mat_info.get("name", f"Unknown ({mat_id})"),
                "service_categories": len(svc_cats),
            })

    # Group by clothing type for summary
    by_type = {}
    for m in missing:
        ct_id = m["clothing_type_id"]
        if ct_id not in by_type:
            by_type[ct_id] = {
                "clothing_type_id": ct_id,
                "clothing_type_name": m["clothing_type_name"],
                "parent_category": m["parent_category"],
                "materials": [],
            }
        by_type[ct_id]["materials"].append({
            "material_id": m["material_id"],
            "material_name": m["material_name"],
        })

    grouped = sorted(by_type.values(), key=lambda x: x["clothing_type_name"])
    return jsonify({
        "total_types_missing": len(grouped),
        "total_combos_missing": len(missing),
        "types": grouped,
    })


@app.route("/docs/category-products")
def docs_category_products():
    """Return sample products that have a given category value.

    Query params:
      - category: the Swedish category string to search for
      - limit: max products to return (default 20)
    """
    category = request.args.get("category", "").strip()
    if not category:
        return jsonify({"error": "category parameter required"}), 400

    limit = min(int(request.args.get("limit", 20)), 100)

    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Search in category, clothing_type columns (case-insensitive)
        cur.execute("""
            SELECT product_id, brand, product_name, category, clothing_type,
                   material_composition, qfix_clothing_type, qfix_material,
                   product_url
            FROM products_unified
            WHERE LOWER(category) LIKE %s
               OR LOWER(clothing_type) LIKE %s
            ORDER BY brand, product_name
            LIMIT %s
        """, (f"%{category.lower()}%", f"%{category.lower()}%", limit))
        products = cur.fetchall()
    conn.close()

    return jsonify({
        "category": category,
        "count": len(products),
        "products": products,
    })


@app.route("/docs/keyword-stats")
def docs_keyword_stats():
    """Return product counts per keyword injection rule."""
    conn = get_db()
    results = []
    with conn.cursor() as cur:
        for rule in KEYWORD_ACTION_RULES:
            # Build OR condition for all keywords in this rule
            conditions = []
            params = []
            for kw in rule["keywords"]:
                conditions.append("LOWER(product_name) LIKE %s OR LOWER(description) LIKE %s")
                params.extend([f"%{kw}%", f"%{kw}%"])

            where = " OR ".join(conditions)
            cur.execute(f"SELECT COUNT(*) FROM products_unified WHERE {where}", params)
            count = cur.fetchone()[0]
            results.append({
                "keywords": rule["keywords"],
                "actions": [a["name"] for a in rule["actions"]],
                "category": rule["category"],
                "product_count": count,
            })
    conn.close()

    total_products = 0
    with get_db() as c2:
        with c2.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM products_unified")
            total_products = cur.fetchone()[0]

    return jsonify({
        "total_products": total_products,
        "rules": results,
    })


@app.route("/remap/validate-keyword-scores", methods=["POST"])
@limiter.limit("2 per minute")
def validate_keyword_scores():
    """Validate keyword injection scoring by asking AI to rank merged action pools.

    Picks sample products per keyword rule, builds the merged pool of AI-ranked +
    keyword-injected actions, and asks Claude to rank them for that specific product.
    Compares AI ranking vs our score-based ranking.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

    _load_qfix_catalog()
    ai_client = anthropic.Anthropic(api_key=api_key)
    conn = get_db()

    samples_per_rule = 2
    comparisons = []

    for rule in KEYWORD_ACTION_RULES:
        # Find sample products that trigger this rule and have a qfix mapping
        conditions = []
        params = []
        for kw in rule["keywords"]:
            conditions.append("(LOWER(product_name) LIKE %s OR LOWER(description) LIKE %s)")
            params.extend([f"%{kw}%", f"%{kw}%"])

        where = " OR ".join(conditions)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT product_id, product_name, description, brand,
                       clothing_type, material_composition,
                       qfix_clothing_type, qfix_clothing_type_id,
                       qfix_material, qfix_material_id
                FROM products_unified
                WHERE ({where}) AND qfix_clothing_type_id IS NOT NULL
                ORDER BY RANDOM()
                LIMIT %s
            """, params + [samples_per_rule])
            products = cur.fetchall()

        for product in products:
            ct_id = product["qfix_clothing_type_id"]
            mat_id = product["qfix_material_id"]

            # Get AI-ranked top 5
            ai_top = get_action_ranking(conn, ct_id, mat_id) or {}
            ai_repair = ai_top.get(rule["category"], [])

            if not ai_repair:
                continue

            # Get the full service list for this clothing type
            svc_cats = _qfix_services.get((ct_id, mat_id), [])
            if not svc_cats:
                continue

            # Build product text and run keyword injection
            product_text = " ".join(filter(None, [
                product.get("product_name", ""),
                product.get("description", ""),
                product.get("clothing_type", ""),
            ])).lower()

            merged = _inject_keyword_actions(ai_top, product_text, svc_cats)
            merged_actions = merged.get(rule["category"], [])

            # Check if injection actually changed the list
            ai_names = {a["name"] for a in ai_repair}
            merged_names = {a["name"] for a in merged_actions}
            if ai_names == merged_names:
                continue  # No injection happened

            # Collect all candidate action names (merged pool)
            action_names = [a["name"] for a in merged_actions]

            # Also include AI actions that got bumped out
            all_candidates = list(action_names)
            for a in ai_repair:
                if a["name"] not in all_candidates:
                    all_candidates.append(a["name"])

            # Ask Claude to rank these for this specific product
            actions_list = "\n".join(f"- {name}" for name in all_candidates)
            prompt = f"""For a specific product: "{product.get('product_name', '')}" ({product.get('qfix_clothing_type', '')} made of {product.get('qfix_material', '')}).

Product description: {(product.get('description') or 'N/A')[:300]}

Rank these {rule['category']} actions by how likely a customer owning THIS SPECIFIC product would need them. Consider the product's specific features mentioned in the name and description.

Available actions:
{actions_list}

Return ONLY a JSON array of the action names ordered by likelihood (most likely first). Return ALL of them, not just top 5."""

            try:
                message = ai_client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                )
                response_text = message.content[0].text.strip()
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    response_text = "\n".join(lines[1:-1])

                ai_ranking = json.loads(response_text)

                # Compare: our score-based top 5 vs AI's top 5
                our_top5 = [a["name"] for a in merged_actions[:5]]
                ai_top5 = ai_ranking[:5]

                # Calculate overlap and position differences
                our_set = set(our_top5)
                ai_set = set(ai_top5)
                overlap = our_set & ai_set
                only_ours = our_set - ai_set
                only_ai = ai_set - our_set

                comparisons.append({
                    "product_id": product["product_id"],
                    "product_name": product.get("product_name"),
                    "brand": product.get("brand"),
                    "clothing_type": product.get("qfix_clothing_type"),
                    "keyword_rule": rule["keywords"],
                    "category": rule["category"],
                    "our_top5": our_top5,
                    "ai_top5": ai_top5,
                    "ai_full_ranking": ai_ranking,
                    "overlap_count": len(overlap),
                    "overlap": list(overlap),
                    "only_in_ours": list(only_ours),
                    "only_in_ai": list(only_ai),
                })

            except Exception as e:
                logger.warning("Failed to validate for product %s: %s",
                              product["product_id"], e)

    conn.close()

    # Summary stats
    if comparisons:
        avg_overlap = sum(c["overlap_count"] for c in comparisons) / len(comparisons)
    else:
        avg_overlap = 0

    return jsonify({
        "total_comparisons": len(comparisons),
        "avg_overlap_out_of_5": round(avg_overlap, 2),
        "comparisons": comparisons,
    })


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    import database
    database.DATABASE_URL = os.environ.get("DATABASE_URL")
    app.run(debug=True, port=8000)
