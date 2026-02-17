import json
import logging
import re
import time

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lindex.com"
_PRODUCT_URL_PATTERN = re.compile(r"/se/p/(\d+)-(\d+)")

# Top-level category paths to crawl for product discovery
CATEGORY_PATHS = [
    "/se/dam/",
    "/se/barn/",
    "/se/baby/",
    "/se/underklaeder/",
    "/se/sport/",
]


def _extract_json_ld(html):
    """Extract JSON-LD Product data from the page."""
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _parse_nuxt_data(html):
    """Parse the __NUXT_DATA__ indexed reference array.

    Nuxt 3 serialises page data as a flat JSON array where objects reference
    values by array index.  We scan for known key names and resolve their
    adjacent value references.
    """
    m = re.search(r'id="__NUXT_DATA__"[^>]*>\s*(\[.*?\])\s*</script>', html, re.DOTALL)
    if not m:
        return {}

    try:
        arr = json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError):
        return {}

    result = {}
    keys_of_interest = {
        "composition", "colorName", "colorGroup", "styleId",
        "washingInstructions", "liningComp", "description", "name",
    }

    for i, v in enumerate(arr):
        if not isinstance(v, str) or v not in keys_of_interest:
            continue
        if i + 1 >= len(arr):
            continue

        next_val = arr[i + 1]

        # Resolve indexed reference
        if isinstance(next_val, int) and 0 <= next_val < len(arr):
            resolved = arr[next_val]
        else:
            resolved = next_val

        # For 'name' and 'description', only keep the first meaningful one
        if v == "name":
            if "name" not in result and isinstance(resolved, str) and len(resolved) > 3:
                result["name"] = resolved
        elif v == "description":
            if "description" not in result and isinstance(resolved, str) and len(resolved) > 5:
                result["description"] = resolved
        else:
            if v not in result and resolved is not None:
                result[v] = resolved

    return result


def _extract_category_links(html):
    """Extract sub-category links from a category page."""
    links = set()
    for m in re.finditer(r'href="(/se/[^"]+/)"', html):
        path = m.group(1)
        # Skip non-category paths
        if "/p/" in path or "/checkout" in path or "/login" in path:
            continue
        links.add(path)
    return links


def _extract_product_urls(html):
    """Extract product URLs from a category/listing page."""
    urls = set()
    for m in _PRODUCT_URL_PATTERN.finditer(html):
        style_id = m.group(1)
        color_id = m.group(2)
        urls.add(f"{BASE_URL}/se/p/{style_id}-{color_id}")
    return urls


def fetch_product_urls(page, delay=1.0):
    """Crawl category pages to discover product URLs.

    Args:
        page: Playwright page object
        delay: seconds to wait between page loads
    """
    all_product_urls = set()
    visited_categories = set()
    categories_to_visit = list(CATEGORY_PATHS)

    while categories_to_visit:
        cat_path = categories_to_visit.pop(0)
        if cat_path in visited_categories:
            continue
        visited_categories.add(cat_path)

        url = f"{BASE_URL}{cat_path}"
        logger.info("Crawling category: %s", url)
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if resp and resp.status == 200:
                html = page.content()
                product_urls = _extract_product_urls(html)
                all_product_urls.update(product_urls)
                logger.info("  Found %d products, %d total so far",
                            len(product_urls), len(all_product_urls))

                # Discover sub-categories
                sub_links = _extract_category_links(html)
                for link in sub_links:
                    if link not in visited_categories:
                        categories_to_visit.append(link)
            else:
                status = resp.status if resp else "none"
                logger.warning("  Got status %s for %s", status, url)
        except Exception as e:
            logger.error("  Error crawling %s: %s", url, e)

        time.sleep(delay)

    logger.info("Found %d unique product URLs from %d categories",
                len(all_product_urls), len(visited_categories))
    return list(all_product_urls)


def scrape_product(page, url):
    """Scrape a single Lindex product page using Playwright.

    Args:
        page: Playwright page object
        url: product URL to scrape

    Returns:
        Product dict or None if extraction fails.
    """
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if not resp or resp.status != 200:
            logger.warning("Got status %s for %s", resp.status if resp else "none", url)
            return None
    except Exception as e:
        logger.error("Failed to load %s: %s", url, e)
        return None

    html = page.content()

    # Try NUXT_DATA first (richer data)
    nuxt = _parse_nuxt_data(html)

    # JSON-LD as fallback/supplement
    json_ld = _extract_json_ld(html) or {}

    # Extract product ID
    product_id = nuxt.get("styleId")
    if not product_id:
        pid = json_ld.get("productID", "")
        # productID format is "styleId-colorId"
        product_id = pid.split("-")[0] if pid else None
    if not product_id:
        m = _PRODUCT_URL_PATTERN.search(url)
        product_id = m.group(1) if m else None

    if not product_id:
        logger.warning("Could not extract product ID from %s, skipping", url)
        return None

    product_name = nuxt.get("name") or json_ld.get("name")
    description = nuxt.get("description") or json_ld.get("description")
    composition = nuxt.get("composition")
    color = nuxt.get("colorName") or nuxt.get("colorGroup")
    image_url = json_ld.get("image")

    return {
        "product_id": product_id,
        "product_name": product_name,
        "category": None,
        "clothing_type": None,
        "material_composition": composition,
        "product_url": str(page.url),
        "description": description,
        "color": color,
        "brand": "Lindex",
        "image_url": image_url,
    }


def scrape_all(page, urls, callback=None, delay=0.5):
    """Scrape all product URLs sequentially using a Playwright page.

    Args:
        page: Playwright page object
        urls: list of product URLs
        callback: function to call with each product dict
        delay: seconds to wait between requests
    """
    total = len(urls)
    done = 0

    for url in urls:
        result = scrape_product(page, url)
        done += 1
        if done % 50 == 0 or done == total:
            logger.info("[%d/%d] Progress update", done, total)
        if result and callback:
            callback(result)
        time.sleep(delay)
