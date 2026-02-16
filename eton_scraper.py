import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
from lxml import etree

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.etonshirts.com/se/sv/sitemap.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

_PRODUCT_URL_PATTERN = re.compile(r"/se/sv/product/")


def fetch_product_urls():
    """Fetch all product URLs from the Eton Shirts sitemap."""
    logger.info("Fetching sitemap: %s", SITEMAP_URL)
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    root = etree.fromstring(resp.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//s:loc", ns)]

    product_urls = [u for u in urls if _PRODUCT_URL_PATTERN.search(u)]
    logger.info("Found %d product URLs", len(product_urls))
    return product_urls


def _extract_json_ld_product(soup):
    """Find and return the JSON-LD ProductGroup object from the page, or None."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") in ("ProductGroup", "Product"):
                return data
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") in ("ProductGroup", "Product"):
                        return entry
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_product_id(product_data):
    """Extract product ID (SKU) from JSON-LD data."""
    if product_data:
        sku = product_data.get("sku")
        if sku:
            return sku
    return None


def _extract_product_name(product_data, soup):
    """Extract product name from JSON-LD or page h1."""
    if product_data:
        name = product_data.get("name")
        if name:
            return name.strip()
    h1 = soup.select_one("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def _extract_description(product_data, soup):
    """Extract product description from JSON-LD or page content."""
    if product_data:
        desc = product_data.get("description")
        if desc:
            return desc.strip()
    return None


def _extract_color(product_data):
    """Extract color from JSON-LD."""
    if product_data:
        color = product_data.get("color")
        if color:
            return color.strip()
    return None


def _extract_material(product_data):
    """Extract material from JSON-LD."""
    if product_data:
        material = product_data.get("material")
        if material:
            return material.strip()
    return None


def _extract_image_url(soup):
    """Extract first product image URL from the page."""
    # Try og:image meta tag
    og_img = soup.select_one('meta[property="og:image"]')
    if og_img and og_img.get("content"):
        return og_img["content"]
    # Try JSON-LD image
    product = _extract_json_ld_product(soup)
    if product:
        img = product.get("image")
        if isinstance(img, list) and img:
            return img[0]
        elif isinstance(img, str) and img:
            return img
    return None


def _extract_clothing_type(soup):
    """Extract clothing type from breadcrumb navigation."""
    # Try JSON-LD BreadcrumbList
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
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
                skip = {"hem", "home", "eton", ""}
                filtered = [n for n in names if n.lower().strip() not in skip]
                # Drop the last item (product name itself)
                if len(filtered) > 1:
                    return " > ".join(filtered[:-1])
                elif filtered:
                    return filtered[0]
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: HTML breadcrumbs
    breadcrumb = soup.select_one("nav[aria-label='breadcrumb'], .breadcrumb, [class*='breadcrumb']")
    if breadcrumb:
        items = breadcrumb.select("a, span, li")
        texts = [item.get_text(strip=True) for item in items if item.get_text(strip=True)]
        skip = {"hem", "home", "eton", ""}
        filtered = [t for t in texts if t.lower().strip() not in skip]
        if len(filtered) > 1:
            return " > ".join(filtered[:-1])
        elif filtered:
            return filtered[0]
    return None


def _extract_category(url):
    """Derive a broad category from the clothing type or URL."""
    # Will be set from clothing_type in scrape_product
    return None


def scrape_product(url, session=None):
    """Scrape a single Eton product page and return a dict."""
    getter = session or requests
    resp = getter.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    product_data = _extract_json_ld_product(soup)

    product_id = _extract_product_id(product_data)
    if not product_id:
        logger.warning("Could not extract product ID from %s, skipping", url)
        return None

    clothing_type = _extract_clothing_type(soup)

    return {
        "product_id": product_id,
        "product_name": _extract_product_name(product_data, soup),
        "category": clothing_type.split(" > ")[0].lower() if clothing_type else None,
        "clothing_type": clothing_type,
        "material_composition": _extract_material(product_data),
        "product_url": url,
        "description": _extract_description(product_data, soup),
        "color": _extract_color(product_data),
        "brand": "Eton",
        "image_url": _extract_image_url(soup),
    }


def scrape_all(urls, callback=None, workers=5):
    """Scrape all product URLs concurrently, calling callback(product_dict) for each."""
    total = len(urls)
    done = 0
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(pool_connections=workers, pool_maxsize=workers)
    session.mount("https://", adapter)

    def _scrape_one(url):
        try:
            return scrape_product(url, session=session)
        except requests.RequestException as e:
            logger.error("Failed to scrape %s: %s", url, e)
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        batch_size = workers * 4
        for batch_start in range(0, total, batch_size):
            batch = urls[batch_start:batch_start + batch_size]
            futures = [pool.submit(_scrape_one, url) for url in batch]
            for future in futures:
                result = future.result()
                done += 1
                if done % 100 == 0 or done == total:
                    logger.info("[%d/%d] Progress update", done, total)
                if result and callback:
                    callback(result)
