# KappAhl & Gina Tricot → QFix API

Maps products from KappAhl and Gina Tricot to [QFix](https://kappahl.dev.qfixr.me) repair service categories, generating ready-to-use repair booking URLs. Also supports image-based product identification via Claude Vision.

**Live API:** https://kappahl-qfix.fly.dev

## Endpoints

### v1 — KappAhl (scraper data)

#### `GET /product/<product_id>`

Look up a KappAhl product by its product ID and get the corresponding QFix repair category and booking URL.

```
GET /product/534008
```

```json
{
  "kappahl": {
    "product_id": "534008",
    "product_name": "Jacka i bomullstwill",
    "category": "herr",
    "clothing_type": "Jackor & rockar > Vårjackor",
    "material_composition": "99% Bomull, 1% Elastan",
    "product_url": "https://www.kappahl.com/sv-se/herr/jackor--rockar/varjackor/534008",
    "description": "En snygg jacka",
    "color": "Svart",
    "brand": "KappAhl"
  },
  "qfix": {
    "qfix_clothing_type": "Jacket",
    "qfix_clothing_type_id": 173,
    "qfix_material": "Standard textile",
    "qfix_material_id": 69,
    "qfix_subcategory": "Men's Clothing",
    "qfix_subcategory_id": 56,
    "qfix_url": "https://kappahl.dev.qfixr.me/sv/?category_id=173&material_id=69"
  }
}
```

#### `GET /products`

List the first 100 KappAhl products.

### v2 — T4V Protocol (xlsx upload)

#### `POST /v2/upload`

Upload a T4V protocol `.xlsx` file to import product data.

#### `GET /v2/product/gtin/<gtin>`

Look up a product by GTIN barcode.

#### `GET /v2/product/article/<article_number>`

Look up all size variants for an article number.

#### `GET /v2/products`

List protocol products (limit 200).

### v3 — Gina Tricot (scraper data)

#### `GET /v3/product/<product_id>`

Look up a Gina Tricot product with QFix mapping.

#### `GET /v3/products`

List Gina Tricot products (limit 200).

#### `GET /v3/product/search?q=<query>`

Search Gina Tricot products by name.

### v4 — Aggregated (scraper + protocol merged)

#### `GET /v4/product/<product_id>`

Get a Gina Tricot product with merged data from both scraper and protocol sources. Returns Swedish description (scraper) + English description (protocol) + care text + country of origin when both sources match.

#### `GET /v4/products`

List aggregated products with merge status (`merged` or `scraper_only`).

#### `GET /v4/product/search?q=<query>`

Search aggregated products by name.

### Vision — Image-based identification

#### `POST /identify`

Upload an image of a garment to identify its type, material, and color using Claude Vision, then get a QFix repair booking URL.

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

Supports JPEG, PNG, WebP, and GIF. Images over 5 MB are automatically resized.

### Unmapped categories

#### `GET /unmapped`

Returns all clothing types and materials from both KappAhl and Gina Tricot that don't currently map to a QFix category. Useful for identifying gaps in the mapping. Also includes the full list of valid QFix categories as reference.

```json
{
  "kappahl": {
    "unmapped_clothing_types": [
      {"clothing_type": "Accessoarer > Smycken > Örhängen", "distinct_products": 4}
    ],
    "unmapped_materials": ["..."]
  },
  "ginatricot": {
    "unmapped_clothing_types": [
      {"clothing_type": "coatsjackets > kappor", "distinct_products": 9}
    ],
    "unmapped_materials": ["..."]
  },
  "qfix_valid_clothing_types": {"Jacket": 173, "Coat": 104, "...": "..."},
  "qfix_valid_materials": {"173": {"69": "Standard textile", "71": "Leather/Suede"}}
}
```

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

## Data coverage

- **~3,148 products** scraped from kappahl.com (dam, herr, barn, baby)
- **~20,597 products** scraped from ginatricot.com (klader, accessoarer)
- **4 products** from T4V protocol xlsx

## How it works

1. **Scrapers** (`scraper.py`, `ginatricot_scraper.py`) fetch product URLs from sitemaps and extract product data (name, clothing type, material, color, brand, images) from each page
2. **Protocol parser** (`protocol_parser.py`) imports structured product data from T4V protocol xlsx files
3. **Mapping** (`mapping.py`, `mapping_v2.py`) translates Swedish/English categories and materials to QFix repair categories with numeric IDs
4. **Vision** (`vision.py`) uses Claude Vision API to classify uploaded garment images into QFix categories
5. **API** (`api.py`) serves everything via Flask, combining product data with QFix mapping on each request

## Running locally

```bash
pip install -r requirements.txt
python api.py
# API available at http://localhost:8000
```

To re-scrape products:

```bash
cp .env.example .env  # Add ANTHROPIC_API_KEY for vision endpoint
python main.py              # KappAhl
python ginatricot_main.py   # Gina Tricot
```

## Tests

```bash
python -m pytest tests/ -v
# 108 tests covering scrapers, database, mapping, API, and vision
```
