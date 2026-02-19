import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

from curl_cffi import requests as cffi_requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lindex.com"
HEADERS = {"Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8"}
_PRODUCT_URL_PATTERN = re.compile(r"/se/p/(\d+)-(\d+)")

# Top-level category paths to crawl for product discovery
CATEGORY_PATHS = [
    "/se/dam/",
    "/se/barn/",
    "/se/baby/",
    "/se/underklader/",
]


def _get(url, session=None):
    """Fetch a URL using curl-cffi with Chrome TLS impersonation."""
    getter = session or cffi_requests
    return getter.get(
        url,
        impersonate="chrome",
        headers=HEADERS,
        timeout=30,
        allow_redirects=True,
    )


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

    Nuxt 3 serialises page data as a flat JSON array where dict entries
    reference values by array index.  We find the main product dict
    (identified by having 'composition' + 'styleId' keys) and resolve refs.
    """
    m = re.search(r'id="__NUXT_DATA__"[^>]*>\s*(\[.*?\])\s*</script>', html, re.DOTALL)
    if not m:
        return {}

    try:
        arr = json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError):
        return {}

    # Find the main product dict (has composition + styleId keys)
    product_keys = {"composition", "styleId", "colorName"}
    for item in arr:
        if isinstance(item, dict) and product_keys.issubset(item.keys()):
            result = {}
            for key in ("styleId", "name", "description", "composition",
                        "colorName", "colorGroup", "washingInstructions",
                        "careInstructions", "liningComp"):
                if key not in item:
                    continue
                ref = item[key]
                if isinstance(ref, int) and 0 <= ref < len(arr):
                    result[key] = arr[ref]
                else:
                    result[key] = ref
            return result

    return {}


def _extract_category_links(html):
    """Extract sub-category links from a category page."""
    links = set()
    for m in re.finditer(r'href="(/se/(?:dam|barn|baby|underklader)/[^"?]+)', html):
        path = m.group(1)
        # Skip product pages
        if "/p/" in path:
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


def _parse_category_path(cat_path):
    """Extract category and clothing_type from a Lindex category path.

    E.g. "/se/dam/klanningar/" -> ("dam", "klänningar")
         "/se/barn/jackor-rockar/" -> ("barn", "jackor & rockar")
         "/se/underklader/bh/" -> ("underkläder", "bh")
    """
    parts = [p for p in cat_path.strip("/").split("/") if p and p != "se"]
    if not parts:
        return None, None

    category = parts[0] if parts else None  # dam, barn, baby, underklader
    clothing_type = None
    if len(parts) > 1:
        # Convert URL slug to readable Swedish: "jackor-rockar" -> "jackor & rockar"
        clothing_type = parts[1].replace("-", " ")
    return category, clothing_type


def fetch_product_urls(session=None, delay=1.0):
    """Crawl category pages to discover product URLs.

    Returns:
        dict mapping product_url -> {"category": str, "clothing_type": str}
    """
    url_to_category = {}
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
            resp = _get(url, session=session)
            if resp.status_code == 200:
                html = resp.text
                product_urls = _extract_product_urls(html)
                category, clothing_type = _parse_category_path(cat_path)
                for purl in product_urls:
                    if purl not in url_to_category:
                        url_to_category[purl] = {
                            "category": category,
                            "clothing_type": clothing_type,
                        }
                logger.info("  Found %d products, %d total so far",
                            len(product_urls), len(url_to_category))

                # Discover sub-categories
                sub_links = _extract_category_links(html)
                for link in sub_links:
                    if link not in visited_categories:
                        categories_to_visit.append(link)
            else:
                logger.warning("  Got status %s for %s", resp.status_code, url)
        except Exception as e:
            logger.error("  Error crawling %s: %s", url, e)

        time.sleep(delay)

    logger.info("Found %d unique product URLs from %d categories",
                len(url_to_category), len(visited_categories))
    return url_to_category


def scrape_product(url, session=None, category=None, clothing_type=None):
    """Scrape a single Lindex product page.

    Returns:
        Product dict or None if extraction fails.
    """
    try:
        resp = _get(url, session=session)
        if resp.status_code != 200:
            logger.warning("Got status %s for %s", resp.status_code, url)
            return None
    except Exception as e:
        logger.error("Failed to load %s: %s", url, e)
        return None

    html = resp.text

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
        url_m = _PRODUCT_URL_PATTERN.search(url)
        product_id = url_m.group(1) if url_m else None

    if not product_id:
        logger.warning("Could not extract product ID from %s, skipping", url)
        return None

    product_name = nuxt.get("name") or json_ld.get("name")
    description = nuxt.get("description") or json_ld.get("description")
    composition = nuxt.get("composition")
    color = nuxt.get("colorName") or nuxt.get("colorGroup")
    image_url = json_ld.get("image")

    # Build care_text from washingInstructions and careInstructions
    care_parts = []
    washing = nuxt.get("washingInstructions")
    if isinstance(washing, str) and washing:
        care_parts.append(washing)
    care = nuxt.get("careInstructions")
    if isinstance(care, list):
        care_parts.extend(str(c) for c in care if c)
    elif isinstance(care, str) and care:
        care_parts.append(care)
    care_text = ". ".join(care_parts) if care_parts else None

    return {
        "product_id": product_id,
        "product_name": product_name,
        "category": category,
        "clothing_type": clothing_type,
        "material_composition": composition,
        "product_url": str(resp.url),
        "description": description,
        "color": color,
        "brand": "Lindex",
        "image_url": image_url,
        "care_text": care_text,
    }


def scrape_all(url_to_category, callback=None, session=None, workers=3, delay=0.3):
    """Scrape all product URLs, calling callback(product_dict) for each.

    Args:
        url_to_category: dict mapping URL -> {"category": str, "clothing_type": str}
    """
    urls = list(url_to_category.keys())
    total = len(urls)
    done = 0

    def _scrape_one(url):
        try:
            cat_info = url_to_category.get(url, {})
            return scrape_product(
                url, session=session,
                category=cat_info.get("category"),
                clothing_type=cat_info.get("clothing_type"),
            )
        except Exception as e:
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
                if done % 50 == 0 or done == total:
                    logger.info("[%d/%d] Progress update", done, total)
                if result and callback:
                    callback(result)
            time.sleep(delay)
