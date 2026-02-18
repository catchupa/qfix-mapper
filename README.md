# QFix Product API

Maps products from Swedish clothing brands to [QFix](https://kappahl.dev.qfixr.me) repair service categories, generating ready-to-use repair booking URLs. Also supports image-based product identification via Claude Vision.

**Live API:** https://kappahl-qfix.fly.dev

**Swagger UI:** https://kappahl-qfix.fly.dev/apidocs

## Supported brands

| Brand | Endpoint prefix | Products |
|-------|----------------|----------|
| KappAhl | `/kappahl/` | ~3,148 |
| Gina Tricot | `/ginatricot/` | ~20,597 |
| Eton | `/eton/` | ~350 |
| Nudie Jeans | `/nudie/` | ~300 |
| Lindex | `/lindex/` | ~2,960 |

## Authentication

Brand product endpoints (`/<brand>/product/<id>` and `/<brand>/products`) require an API key when the `API_KEYS` environment variable is set. Pass the key via the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-key-here" https://kappahl-qfix.fly.dev/kappahl/product/530956
```

Without a valid key, these endpoints return `401`:

```json
{"error": "Invalid or missing API key"}
```

If `API_KEYS` is not set, authentication is disabled and all requests are allowed. Other endpoints (`/demo`, `/widget.js`, `/apidocs`, `/v2/*`, `/v3/*`, `/v4/*`) do not require authentication.

To configure keys on Fly.io (format `brand:key,brand:key`):

```bash
flyctl secrets set API_KEYS="kappahl:your-key,lindex:another-key"
```

## Endpoints

### Brand product endpoints

All five brands follow the same pattern:

#### `GET /<brand>/product/<product_id>`

Look up a product by ID with QFix repair category mapping.

```
GET /kappahl/product/534008
GET /ginatricot/product/225549000
GET /eton/product/2567-00-10
GET /nudie/product/115053
GET /lindex/product/3010022
```

Response includes QFix catalog enrichment — item metadata, material info, and available repair services grouped by service category (Repair, Adjust measurements, Washing and Care, Other adjustments). Services are filtered by the specific (clothing type, material) combination, matching the QFix website behavior.

```json
{
  "<brand>": {
    "product_id": "534008",
    "product_name": "Jacka i bomullstwill",
    "category": "herr",
    "clothing_type": "Jackor & rockar > Vårjackor",
    "material_composition": "99% Bomull, 1% Elastan",
    "product_url": "https://www.kappahl.com/...",
    "description": "En snygg jacka",
    "color": "Svart",
    "brand": "KappAhl"
  },
  "qfix": {
    "qfix_clothing_type": "Jacket",
    "qfix_clothing_type_id": 93,
    "qfix_material": "Standard textile",
    "qfix_material_id": 69,
    "qfix_subcategory": "Men's Clothing",
    "qfix_subcategory_id": 56,
    "qfix_url": "https://kappahl.dev.qfixr.me/sv/?category_id=93&material_id=69",
    "qfix_item": {
      "id": 93,
      "name": "Jacket",
      "slug": "jacket-mens",
      "parent": { "id": 56, "name": "Men's Clothing" }
    },
    "qfix_subitem": {
      "id": 69,
      "name": "Standard textile",
      "slug": "standardtextile"
    },
    "qfix_services": [
      {
        "id": 37,
        "name": "Repair",
        "services": [
          {
            "id": 1443,
            "name": "Repair seam",
            "price": 254,
            "variants": [
              { "id": 1444, "name": "Repair seam - <10 cm", "price": "254" },
              { "id": 1445, "name": "Repair seam - 10-25 cm", "price": "294" }
            ]
          }
        ]
      },
      { "id": 39, "name": "Adjust measurements", "services": ["..."] },
      { "id": 42, "name": "Washing and Care", "services": ["..."] },
      { "id": 40, "name": "Other adjustments", "services": ["..."] }
    ]
  }
}
```

#### `GET /<brand>/products`

List products for a brand (limit 100).

```
GET /kappahl/products
GET /ginatricot/products
GET /eton/products
GET /nudie/products
GET /lindex/products
```

### Legacy endpoints

KappAhl and Gina Tricot also have legacy route aliases:

| Legacy route | Same as |
|-------------|---------|
| `GET /product/<id>` | `GET /kappahl/product/<id>` |
| `GET /products` | `GET /kappahl/products` |
| `GET /v3/product/<id>` | `GET /ginatricot/product/<id>` (different response format) |
| `GET /v3/products` | `GET /ginatricot/products` |
| `GET /v3/product/search?q=` | Gina Tricot product search |

### T4V Protocol (v2)

#### `POST /v2/upload`

Upload a T4V protocol `.xlsx` file to import structured product data.

#### `GET /v2/product/gtin/<gtin>`

Look up a product by GTIN barcode.

#### `GET /v2/product/article/<article_number>`

Look up all size variants for an article number.

#### `GET /v2/products`

List protocol products (limit 200).

### Aggregated data (v4)

Merges Gina Tricot scraper data with T4V protocol data when both sources match by product name.

#### `GET /v4/product/<product_id>`

Returns merged data: Swedish description (scraper) + English description (protocol) + care text + country of origin. The `source` field is `"merged"` or `"scraper_only"`.

#### `GET /v4/products`

List aggregated products with merge status.

#### `GET /v4/product/search?q=<query>`

Search aggregated products by name.

### Vision — Image identification

#### `POST /identify`

Upload a garment image to identify its type, material, and color using Claude Vision, then get a QFix repair booking URL.

```bash
curl -X POST -F "image=@photo.jpg" https://kappahl-qfix.fly.dev/identify
```

```json
{
  "classification": {
    "clothing_type": "Sweatshirt / Hoodie",
    "material": "Standard textile",
    "color": "Gray",
    "category": "Women's Clothing"
  },
  "qfix": {
    "qfix_clothing_type": "Sweatshirt / Hoodie",
    "qfix_clothing_type_id": 196,
    "qfix_material": "Standard textile",
    "qfix_material_id": null,
    "qfix_subcategory": "Women's Clothing",
    "qfix_subcategory_id": 55,
    "qfix_url": "https://kappahl.dev.qfixr.me/sv/?category_id=196"
  }
}
```

Supports JPEG, PNG, WebP, and GIF. Max 20 MB.

### Unmapped categories

#### `GET /unmapped`

Returns clothing types and materials from all brands that don't currently map to a QFix category. Includes the full list of valid QFix categories as reference. Useful for identifying gaps in the mapping.

#### `POST /unmapped/add`

Add a new clothing type or material mapping at runtime.

```bash
# Map a clothing type
curl -X POST -H "Content-Type: application/json" \
  -d '{"type": "clothing_type", "from": "coatsjackets > kappor", "to": "Coat"}' \
  https://kappahl-qfix.fly.dev/unmapped/add

# Map a material
curl -X POST -H "Content-Type: application/json" \
  -d '{"type": "material", "from": "neopren", "to": "Standard textile"}' \
  https://kappahl-qfix.fly.dev/unmapped/add
```

Note: Mappings added via this endpoint are in-memory only and will be reset on redeploy.

## How it works

1. **Scrapers** (`scraper.py`, `ginatricot_scraper.py`, `eton_scraper.py`, `nudie_scraper.py`, `lindex_scraper.py`) fetch product URLs and extract product data (name, clothing type, material, color, brand, images) from each brand's website
2. **Protocol parser** (`protocol_parser.py`) imports structured product data from T4V protocol xlsx files
3. **Mapping** (`mapping.py`, `mapping_v2.py`) translates Swedish/English categories and materials to QFix repair categories with numeric IDs, using gender-aware resolution (Men's/Women's/Children's clothing map to different QFix category IDs)
4. **QFix catalog enrichment** — on first request, the API fetches the full QFix product-categories tree and caches it in memory. Each product response is enriched with item metadata, material info, and available repair services filtered by the exact (clothing type, material) pair
5. **Vision** (`vision.py`) uses Claude Vision API to classify uploaded garment images into QFix categories
6. **API** (`api.py`) serves everything via Flask with Swagger documentation, combining product data with QFix mapping and catalog enrichment on each request

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env  # Add DATABASE_URL and ANTHROPIC_API_KEY
python api.py
# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/apidocs
```

To re-scrape products:

```bash
python main.py              # KappAhl
python ginatricot_main.py   # Gina Tricot
python eton_main.py         # Eton
python nudie_main.py        # Nudie Jeans
python lindex_main.py       # Lindex
```

## Tests

```bash
python -m pytest tests/ -v
```
