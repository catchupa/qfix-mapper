import html
import re
import time
import json
import logging
import requests
from bs4 import BeautifulSoup
from lxml import etree

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.ginatricot.com/market_sitemaps/se/sitemap.xml"
REQUEST_DELAY = 1.5  # seconds between requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CATEGORIES = ["/se/klader/", "/se/accessoarer/"]

# Product URLs end with a numeric product ID, e.g. /structure-maxi-skirt-225549000
_PRODUCT_URL_PATTERN = re.compile(r"-(\d{6,})$")


def fetch_product_urls():
    """Fetch all product URLs from the Gina Tricot sitemap."""
    logger.info("Fetching sitemap: %s", SITEMAP_URL)
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    root = etree.fromstring(resp.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//s:loc", ns)]

    product_urls = [
        u for u in urls
        if any(cat in u for cat in CATEGORIES)
        and _PRODUCT_URL_PATTERN.search(u.rstrip("/"))
    ]
    logger.info("Found %d product URLs (klader + accessoarer)", len(product_urls))
    return product_urls


def _extract_product_id(url):
    """Extract trailing numeric product ID from URL."""
    match = _PRODUCT_URL_PATTERN.search(url.rstrip("/"))
    if match:
        return match.group(1)
    return None


def _extract_category(url):
    if "/se/klader/" in url:
        return "klader"
    if "/se/accessoarer/" in url:
        return "accessoarer"
    return None


def _extract_json_ld_product(soup):
    """Find and return the JSON-LD Product object from the page, or None."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            raw = script.string or ""
            # Gina Tricot HTML-encodes JSON-LD content (&quot; instead of ")
            unescaped = html.unescape(raw)
            data = json.loads(unescaped)
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
                        return entry
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_clothing_type(soup):
    """Extract clothing type from breadcrumb navigation."""
    # Try JSON-LD BreadcrumbList first
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            raw = script.string or ""
            data = json.loads(html.unescape(raw))
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
                # Skip home, brand, and top-level category
                skip = {"hem", "home", "gina tricot", "klader", "kläder", "accessoarer"}
                filtered = [n for n in names if n.lower().strip() not in skip]
                if filtered:
                    return " > ".join(filtered)
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: HTML breadcrumbs
    breadcrumb = soup.select_one("nav[aria-label='breadcrumb'], .breadcrumb, [class*='breadcrumb']")
    if breadcrumb:
        items = breadcrumb.select("a, span, li")
        texts = [item.get_text(strip=True) for item in items if item.get_text(strip=True)]
        skip = {"hem", "home", "gina tricot", "klader", "kläder", "accessoarer", ""}
        filtered = [t for t in texts if t.lower().strip() not in skip]
        if filtered:
            return " > ".join(filtered)

    return None


def _extract_clothing_type_from_url(url):
    """Extract clothing type from URL path segments as fallback.

    URL pattern: /se/{category}/{subcategory}/{type}/{name}-{id}
    e.g. /se/klader/kjolar/langkjolar/structure-maxi-skirt-225549000
    -> "kjolar > langkjolar"
    """
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path.rstrip("/")
        parts = path.split("/")
        # Expected: ['', 'se', 'klader', 'kjolar', 'langkjolar', 'structure-maxi-skirt-225549000']
        skip = {"", "se", "klader", "accessoarer"}
        # Drop first segments and the last one (product slug)
        middle = [p for p in parts[:-1] if p not in skip]
        if middle:
            return " > ".join(middle)
    except Exception:
        pass
    return None


def _extract_product_name(soup):
    """Extract product name from JSON-LD or page title."""
    product = _extract_json_ld_product(soup)
    if product:
        name = product.get("name")
        if name:
            return name.strip()

    h1 = soup.select_one("h1")
    if h1:
        return h1.get_text(strip=True)
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
    """Extract brand from JSON-LD Product.brand."""
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
    """Extract color from JSON-LD Product.color, stripping the code suffix."""
    product = _extract_json_ld_product(soup)
    if product:
        color = product.get("color")
        if color:
            # Strip color code suffix like "(9000)"
            clean = re.sub(r"\s*\(\d+\)\s*$", "", color).strip()
            return clean if clean else color.strip()
    return None


def _extract_material(soup):
    """Extract material composition from JSON-LD Product.material."""
    product = _extract_json_ld_product(soup)
    if product:
        material = product.get("material")
        if material:
            return material.strip()
    return None


def scrape_product(url):
    """Scrape a single Gina Tricot product page and return a dict."""
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
        "clothing_type": _extract_clothing_type(soup) or _extract_clothing_type_from_url(url),
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
