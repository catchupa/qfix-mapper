import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from curl_cffi import requests as cffi_requests
from database import get_connection, create_table_lindex, upsert_product_lindex
from lindex_scraper import fetch_product_urls, scrape_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Connecting to database...")
    conn = get_connection()
    create_table_lindex(conn)

    session = cffi_requests.Session(impersonate="chrome")

    logger.info("Crawling category pages for product URLs...")
    urls = fetch_product_urls(session=session, delay=1.0)
    if not urls:
        logger.warning("No product URLs found. Exiting.")
        conn.close()
        return

    logger.info("Starting to scrape %d products...", len(urls))
    count = {"saved": 0}

    def on_product(product):
        upsert_product_lindex(conn, product)
        count["saved"] += 1

    scrape_all(urls, callback=on_product, session=session, workers=3, delay=0.3)

    logger.info("Done! Saved %d products total.", count["saved"])
    conn.close()


if __name__ == "__main__":
    main()
