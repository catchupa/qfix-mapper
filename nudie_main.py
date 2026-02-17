import logging
import sys
import threading
from dotenv import load_dotenv

load_dotenv()

from database import get_connection, create_table, upsert_product
from nudie_scraper import fetch_product_urls, scrape_all

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

    logger.info("Fetching Nudie Jeans product URLs from sitemap...")
    urls = fetch_product_urls()
    if not urls:
        logger.warning("No product URLs found. Exiting.")
        conn.close()
        return

    logger.info("Starting to scrape %d products...", len(urls))
    count = {"saved": 0}
    lock = threading.Lock()

    def on_product(product):
        with lock:
            upsert_product(conn, product)
            count["saved"] += 1

    scrape_all(urls, callback=on_product, workers=5)

    logger.info("Done! Saved %d products total.", count["saved"])
    conn.close()


if __name__ == "__main__":
    main()
