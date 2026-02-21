import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from curl_cffi import requests as cffi_requests
from database import get_connection, create_table, run_scraper
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
    create_table(conn)
    conn.close()

    session = cffi_requests.Session(impersonate="chrome")

    logger.info("Crawling category pages for product URLs...")
    url_to_category = fetch_product_urls(session=session, delay=1.0)
    if not url_to_category:
        logger.warning("No product URLs found. Exiting.")
        return

    logger.info("Starting to scrape %d products...", len(url_to_category))

    def scrape(on_product):
        scrape_all(url_to_category, callback=on_product, session=session, workers=3, delay=0.3)

    run_scraper(scrape, brand="Lindex")


if __name__ == "__main__":
    main()
