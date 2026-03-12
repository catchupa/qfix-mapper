"""One-time database setup script.

Run this to create the products_unified table and all required columns.
Only needed when setting up a fresh database.

Usage: python setup_db.py
"""
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from database import get_connection, create_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Connecting to database...")
    conn = get_connection()
    logger.info("Creating tables and columns...")
    create_table(conn)
    conn.close()
    logger.info("Database setup complete.")


if __name__ == "__main__":
    main()
