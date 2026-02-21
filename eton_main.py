import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from database import get_connection, create_table, run_scraper
from eton_scraper import fetch_product_urls, scrape_all

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

    logger.info("Fetching Eton product URLs from sitemap...")
    urls = fetch_product_urls()
    if not urls:
        logger.warning("No product URLs found. Exiting.")
        return

    logger.info("Starting to scrape %d products...", len(urls))

    def scrape(on_product):
        scrape_all(urls, callback=on_product, workers=5)

    run_scraper(scrape, brand="Eton")


if __name__ == "__main__":
    main()
