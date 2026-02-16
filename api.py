import os
import sqlite3
from flask import Flask, jsonify

from mapping import map_product

app = Flask(__name__)
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "products.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/product/<product_id>")
def get_product(product_id):
    conn = get_db()
    row = conn.execute(
        "SELECT product_id, product_name, category, clothing_type, material_composition, product_url FROM products WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Product {product_id} not found"}), 404

    product = dict(row)
    qfix = map_product(product)

    return jsonify({
        "kappahl": product,
        "qfix": qfix,
    })


@app.route("/products")
def list_products():
    conn = get_db()
    rows = conn.execute(
        "SELECT product_id, product_name, category, clothing_type FROM products ORDER BY product_id LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(debug=True, port=8000)
