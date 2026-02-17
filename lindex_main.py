import logging
import sys
from dotenv import load_dotenv

load_dotenv()

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

    logger.info("Launching browser...")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="sv-SE",
        )
        page = context.new_page()
        page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        logger.info("Crawling category pages for product URLs...")
        urls = fetch_product_urls(page, delay=1.0)
        if not urls:
            logger.warning("No product URLs found. Exiting.")
            browser.close()
            conn.close()
            return

        logger.info("Starting to scrape %d products...", len(urls))
        count = {"saved": 0}

        def on_product(product):
            upsert_product_lindex(conn, product)
            count["saved"] += 1

        scrape_all(page, urls, callback=on_product, delay=0.5)

        logger.info("Done! Saved %d products total.", count["saved"])
        browser.close()

    conn.close()


if __name__ == "__main__":
    main()
