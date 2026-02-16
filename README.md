# KappAhl → QFix API

Maps KappAhl products to [QFix](https://kappahl.dev.qfixr.me) repair service categories, generating ready-to-use repair booking URLs.

**Live API:** https://kappahl-qfix.fly.dev

## Endpoints

### `GET /product/<product_id>`

Look up a KappAhl product by its product ID and get the corresponding QFix repair category and booking URL.

**Example:**

```
GET https://kappahl-qfix.fly.dev/product/534008
```

**Response:**

```json
{
  "kappahl": {
    "product_id": "534008",
    "product_name": "Jacka i bomullstwill",
    "category": "herr",
    "clothing_type": "Jackor & rockar > Vårjackor",
    "material_composition": "99% Bomull, 1% Elastan",
    "product_url": "https://www.kappahl.com/sv-se/herr/jackor--rockar/varjackor/534008"
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

The `qfix_url` is a direct link to the QFix repair booking page with the correct category and material pre-selected.

### `GET /products`

List the first 100 products in the database.

**Example:**

```
GET https://kappahl-qfix.fly.dev/products
```

**Response:**

```json
[
  {
    "product_id": "172155",
    "product_name": "Slim jeans",
    "category": "herr",
    "clothing_type": "Jeans > Slim fit"
  },
  ...
]
```

## Data coverage

- **3,140 products** scraped from kappahl.com (dam, herr, barn, baby)
- **2,805 products** have valid QFix URLs
- 335 products can't be mapped (accessories like jewelry/sunglasses, or clothing types not in QFix)

## How it works

1. **Scraper** (`scraper.py`) fetches all product URLs from the KappAhl sitemap and extracts product name, clothing type (from breadcrumbs), and material composition (from embedded JSON data) for each product
2. **Mapping** (`mapping.py`) translates Swedish KappAhl categories and materials to English QFix repair categories, resolving the correct numeric IDs per clothing type
3. **API** (`api.py`) serves the data via Flask, combining KappAhl product data with QFix mapping on each request

## Running locally

```bash
pip install -r requirements.txt
python api.py
# API available at http://localhost:8000
```

To re-scrape products:

```bash
cp .env.example .env
python main.py
```
