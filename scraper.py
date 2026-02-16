import re
import time
import json
import logging
import requests
from bs4 import BeautifulSoup
from lxml import etree

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.kappahl.com/sitemap.xml?batch=0&language=sv-se"
REQUEST_DELAY = 1.5  # seconds between requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


CATEGORIES = ["/sv-se/dam/", "/sv-se/herr/", "/sv-se/barn/", "/sv-se/baby/"]


def fetch_product_urls():
    """Fetch all product URLs from the sitemap."""
    logger.info("Fetching sitemap: %s", SITEMAP_URL)
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    root = etree.fromstring(resp.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//s:loc", ns)]

    product_urls = [
        u for u in urls
        if any(cat in u for cat in CATEGORIES)
    ]
    logger.info("Found %d product URLs (dam + herr)", len(product_urls))
    return product_urls


def _extract_product_id(url):
    """Extract trailing numeric product ID from URL."""
    match = re.search(r"/p/(\d+)", url)
    if match:
        return match.group(1)
    # fallback: last path segment if numeric
    parts = url.rstrip("/").split("/")
    for part in reversed(parts):
        if part.isdigit():
            return part
    return None


def _extract_category(url):
    if "/sv-se/dam/" in url:
        return "dam"
    if "/sv-se/herr/" in url:
        return "herr"
    if "/sv-se/barn/" in url:
        return "barn"
    if "/sv-se/baby/" in url:
        return "baby"
    return None


def _extract_clothing_type(soup):
    """Extract clothing type from breadcrumb navigation."""
    breadcrumb = soup.select_one("nav[aria-label='breadcrumb'], .breadcrumb, [class*='breadcrumb']")
    if breadcrumb:
        items = breadcrumb.select("a, span, li")
        texts = [item.get_text(strip=True) for item in items if item.get_text(strip=True)]
        # Skip "Hem" / home and the category (dam/herr), keep the rest
        filtered = []
        for t in texts:
            low = t.lower()
            if low in ("hem", "home", "dam", "herr", "kappahl", ""):
                continue
            filtered.append(t)
        if filtered:
            return " > ".join(filtered)

    # Fallback: try JSON-LD breadcrumb
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
            candidates = []
            if isinstance(data, dict) and data.get("@type") == "BreadcrumbList":
                candidates = [data]
            elif isinstance(data, list):
                candidates = [e for e in data if isinstance(e, dict) and e.get("@type") == "BreadcrumbList"]
            for bc in candidates:
                items = bc.get("itemListElement", [])
                sorted_items = sorted(items, key=lambda x: x.get("position", 0))
                names = []
                for item in sorted_items:
                    name = item.get("name") or (item.get("item", {}) or {}).get("name", "")
                    if name:
                        names.append(name)
                filtered = [n for n in names if n.lower() not in ("hem", "home", "dam", "herr", "kappahl", "")]
                if filtered:
                    return " > ".join(filtered)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_product_name(soup):
    """Extract product name from JSON-LD or page title."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data.get("name")
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
                        return entry.get("name")
        except (json.JSONDecodeError, TypeError):
            continue

    h1 = soup.select_one("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def _extract_json_ld_product(soup):
    """Find and return the JSON-LD Product object from the page, or None."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
                        return entry
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_description(soup):
    """Extract product description from JSON-LD Product.description."""
    product = _extract_json_ld_product(soup)
    if product:
        desc = product.get("description")
        if desc:
            return desc.strip()
    return None


def _extract_brand(soup):
    """Extract brand from JSON-LD Product.brand.name."""
    product = _extract_json_ld_product(soup)
    if product:
        brand = product.get("brand")
        if isinstance(brand, dict):
            name = brand.get("name")
            if name:
                return name.strip()
        elif isinstance(brand, str) and brand:
            return brand.strip()
    return None


def _extract_color(soup):
    """Extract color from visible page text matching 'Färg: ...' pattern."""
    # Look for "Färg:" in visible text
    text = soup.get_text(" ", strip=True)
    match = re.search(r'Färg:\s*([A-Za-zÀ-ÿ0-9 /&-]+?)(?:\s+Storlek|\s+Material|\s+Detaljer|\s*$)', text)
    if match:
        return match.group(1).strip()

    # Fallback: look for JSON-LD Product.color
    product = _extract_json_ld_product(soup)
    if product:
        color = product.get("color")
        if color:
            return color.strip()
    return None


KNOWN_MATERIALS = {
    "polyester", "bomull", "elastan", "polyamid", "viskos", "nylon", "akryl",
    "ull", "lin", "lyocell", "modal", "siden", "cupro", "kashmir", "kasjmir",
    "rayon", "spandex", "silke", "ramie", "jute", "hemp", "hampa", "tencel",
    "acetat", "polyuretan", "gummi", "latex", "läder", "skinn", "metall",
    "mässing", "zink", "silver", "guld", "koppar", "stål", "järn", "tenn",
    # common prefixed forms
    "ekologisk bomull", "återvunnen polyester", "återvunnen polyamid",
    "återvunnen bomull", "återvunnen ull", "återvunnen metall",
    "certifierad ull", "certifierad bomull",
    "vegetabiliskt garvat", "regenererad nylon",
}

# Build a regex alternation from known materials (longest first to match greedily)
_material_names = sorted(KNOWN_MATERIALS, key=len, reverse=True)
_MATERIAL_PATTERN = re.compile(
    r"(\d{1,3})\s*%\s*(" + "|".join(re.escape(m) for m in _material_names) + r")",
    re.IGNORECASE,
)


def _extract_material_from_text(text):
    """Try to find material percentages in a text string using known materials."""
    matches = _MATERIAL_PATTERN.findall(text)
    if not matches:
        return None
    compositions = [f"{pct}% {name}" for pct, name in matches]
    seen = set()
    unique = []
    for c in compositions:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return ", ".join(unique[:10]) if unique else None


def _extract_material(soup):
    """Extract material composition from the page."""
    # Primary: look for materialDescriptions in inline JS/JSON data
    # KappAhl embeds product data as JSON in script tags with materialInformation
    for script in soup.find_all("script"):
        script_text = script.string or ""
        match = re.search(r'"materialDescriptions"\s*:\s*\[(.*?)\]', script_text, re.DOTALL)
        if match:
            # Parse the array content: ["Huvudmaterial: 99% Bomull, 1% Elastan", ...]
            try:
                descriptions = json.loads("[" + match.group(1) + "]")
                combined = " ".join(descriptions)
                result = _extract_material_from_text(combined)
                if result:
                    return result
            except (json.JSONDecodeError, TypeError):
                pass

    # Fallback: search visible page text
    text = soup.get_text(" ", strip=True)
    result = _extract_material_from_text(text)
    if result:
        return result

    # Fallback: check JSON-LD product description
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
            descs = []
            if isinstance(data, dict) and data.get("@type") == "Product":
                descs.append(data.get("description", ""))
            elif isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
                        descs.append(entry.get("description", ""))
            for desc in descs:
                result = _extract_material_from_text(desc)
                if result:
                    return result
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def scrape_product(url):
    """Scrape a single product page and return a dict."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    product_id = _extract_product_id(url)
    if not product_id:
        logger.warning("Could not extract product ID from %s, skipping", url)
        return None

    return {
        "product_id": product_id,
        "product_name": _extract_product_name(soup),
        "category": _extract_category(url),
        "clothing_type": _extract_clothing_type(soup),
        "material_composition": _extract_material(soup),
        "product_url": url,
        "description": _extract_description(soup),
        "color": _extract_color(soup),
        "brand": _extract_brand(soup),
    }


def scrape_all(urls, callback=None):
    """Scrape all product URLs, calling callback(product_dict) for each."""
    total = len(urls)
    for i, url in enumerate(urls, 1):
        logger.info("[%d/%d] Scraping %s", i, total, url)
        try:
            product = scrape_product(url)
            if product and callback:
                callback(product)
        except requests.RequestException as e:
            logger.error("Failed to scrape %s: %s", url, e)
        time.sleep(REQUEST_DELAY)
