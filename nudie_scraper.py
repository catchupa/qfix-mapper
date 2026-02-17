import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
from lxml import etree

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.nudiejeans.com/en-SE/sitemap/products.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

_PRODUCT_URL_PATTERN = re.compile(r"/en-SE/product/")


def fetch_product_urls():
    """Fetch all product URLs from the Nudie Jeans sitemap."""
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
    """Find and return the JSON-LD Product object from the page, or None."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
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
        if desc and desc.strip():
            return desc.strip()
    # Fallback: try meta description
    if soup:
        meta = soup.select_one('meta[name="description"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
    return None


_COMPOSITION_PATTERN = re.compile(
    r'pr_composition.*?\\"value\\":\\"([^\\]+)\\"'
)

_COLOR_PATTERN = re.compile(
    r'pr_color.*?\\"value\\":\\"([^\\]+)\\"'
)


def _extract_material_composition(html):
    """Extract material composition from the Next.js RSC flight payload.

    Nudie embeds product attributes (including pr_composition) in
    self.__next_f.push() script blocks within the HTML.
    """
    m = _COMPOSITION_PATTERN.search(html)
    return m.group(1) if m else None


def _extract_color(html):
    """Extract color from the Next.js RSC flight payload (pr_color attribute)."""
    m = _COLOR_PATTERN.search(html)
    return m.group(1) if m else None


def _extract_brand(product_data):
    """Extract brand from JSON-LD."""
    if product_data:
        brand = product_data.get("brand")
        if isinstance(brand, dict):
            return brand.get("name", "").strip() or "Nudie Jeans"
        elif isinstance(brand, str) and brand:
            return brand.strip()
    return "Nudie Jeans"


def _extract_image_url(product_data, soup):
    """Extract product image URL."""
    if product_data:
        img = product_data.get("image")
        if isinstance(img, list) and img:
            return img[0]
        elif isinstance(img, str) and img:
            return img
    # Fallback: og:image
    og_img = soup.select_one('meta[property="og:image"]')
    if og_img and og_img.get("content"):
        return og_img["content"]
    return None


def _extract_clothing_type(soup):
    """Extract clothing type from breadcrumb navigation."""
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
                skip = {"home", "hem", "nudie jeans", ""}
                filtered = [n for n in names if n.lower().strip() not in skip]
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
        skip = {"home", "hem", "nudie jeans", ""}
        filtered = [t for t in texts if t.lower().strip() not in skip]
        if len(filtered) > 1:
            return " > ".join(filtered[:-1])
        elif filtered:
            return filtered[0]
    return None


def _extract_category_from_url(url):
    """Derive category from URL path slug for fallback."""
    # Only check the product slug (last path segment), not the full URL/domain
    lower = url.lower().rsplit("/", 1)[-1]
    if "jeans" in lower or "denim" in lower:
        return "jeans"
    if "jacket" in lower:
        return "jackets"
    if "shirt" in lower:
        return "shirts"
    if "t-shirt" in lower or "tshirt" in lower or "tee" in lower:
        return "t-shirts"
    if "pant" in lower or "trouser" in lower:
        return "pants"
    if "short" in lower:
        return "shorts"
    if "knit" in lower or "sweat" in lower:
        return "knitwear"
    if "sock" in lower:
        return "socks"
    if "dress" in lower or "skirt" in lower:
        return "dresses"
    return None


def scrape_product(url, session=None):
    """Scrape a single Nudie Jeans product page and return a dict."""
    getter = session or requests
    resp = getter.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    product_data = _extract_json_ld_product(soup)

    product_id = _extract_product_id(product_data)
    if not product_id:
        logger.warning("Could not extract product ID from %s, skipping", url)
        return None

    product_name = _extract_product_name(product_data, soup)
    clothing_type = _extract_clothing_type(soup)

    return {
        "product_id": product_id,
        "product_name": product_name,
        "category": clothing_type.split(" > ")[0].lower() if clothing_type else _extract_category_from_url(url),
        "clothing_type": clothing_type,
        "material_composition": _extract_material_composition(html),
        "product_url": url,
        "description": _extract_description(product_data, soup),
        "color": _extract_color(html),
        "brand": _extract_brand(product_data),
        "image_url": _extract_image_url(product_data, soup),
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
