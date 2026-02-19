import logging
import sys
import threading
from dotenv import load_dotenv

load_dotenv()

from database import get_connection, create_table, upsert_product
from ginatricot_scraper import fetch_product_urls, scrape_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Connecting to database...")
    conn = get_connection()
    create_table(conn)

    logger.info("Fetching Gina Tricot product URLs from sitemap...")
    urls = fetch_product_urls()
    if not urls:
        logger.warning("No product URLs found. Exiting.")
        conn.close()
        return

    logger.info("Starting to scrape %d products...", len(urls))
    count = {"saved": 0}
    lock = threading.Lock()

    pending = []

    def on_product(product):
        product["sub_brand"] = product.get("brand")
        product["brand"] = "Gina Tricot"
        with lock:
            pending.append(product)
            if len(pending) >= 50:
                _flush(pending, count)

    def _flush(products, cnt):
        if not products:
            return
        batch = list(products)
        products.clear()
        for attempt in range(3):
            try:
                c = get_connection()
                for p in batch:
                    upsert_product(c, p)
                    cnt["saved"] += 1
                c.close()
                return
            except Exception as e:
                logger.warning("DB write failed (attempt %d/3): %s", attempt + 1, e)
                if attempt < 2:
                    import time
                    time.sleep(2 ** attempt)
        logger.error("Giving up on batch of %d products after 3 attempts", len(batch))

    scrape_all(urls, callback=on_product, workers=3)
    _flush(pending, count)

    logger.info("Done! Saved %d products total.", count["saved"])


if __name__ == "__main__":
    main()
