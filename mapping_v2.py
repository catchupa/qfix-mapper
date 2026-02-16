"""
Maps T4V protocol product data (English) to QFix repair service categories.

Uses the same QFix IDs as mapping.py but maps from English category/material
names found in T4V Public Data Protocol xlsx files.
"""
import re

from mapping import QFIX_CLOTHING_TYPE_IDS, QFIX_SUBCATEGORY_IDS, VALID_MATERIAL_IDS, _resolve_material_id

# ── Product Group (from protocol) → QFix clothing type ──────────────────

PRODUCT_GROUP_MAP = {
    # Direct matches
    "denim": "Trousers",
    "jacket": "Jacket",
    "outwear": "Jacket",
    "coat": "Coat",
    "dress": "Skirt / Dress",
    "skirt": "Skirt / Dress",
    "t-shirt": "T-shirt",
    "sweater": "Sweater",
    "pants": "Trousers",
    "blouse": "Shirt / Blouse",
    "shirt": "Shirt / Blouse",
    "top": "Top / T-shirt",
    "body": "Underwear",
    "overall": "Overall",
    "vests": "Unlined Jacket / Vest",
    "blazer": "Suit",
    "cap": "Cap",
    "gloves": "Gloves",
    "scarf": "Scarf / Shawl",
    "belt": "Belt",
    "handbags": "Handbags",
    "backpack": "Handbags",
    "bag": "Handbags",
    "socks": "Underwear",
    "tights": "Underwear",
    "pyjamas": "Underwear",
    "nightdress": "Underwear",
    "sportswear": "Sweatshirt / Hoodie",
    "swimwear - bottom": "Swimsuit",
    "swimwear - one piece": "Swimsuit",
    "swimwear - top": "Bikini",
}

# Keywords in product name → QFix type (for ambiguous categories like "Knitwear")
PRODUCT_NAME_KEYWORDS = [
    ("skirt", "Skirt / Dress"),
    ("dress", "Skirt / Dress"),
    ("top", "Knitted Jumper"),
    ("jumper", "Knitted Jumper"),
    ("cardigan", "Knitted Jumper"),
    ("sweater", "Sweater"),
    ("vest", "Unlined Jacket / Vest"),
    ("pants", "Trousers"),
    ("trouser", "Trousers"),
]

# ── English material name → QFix material category ──────────────────────

MATERIAL_MAP_EN = {
    # Standard textiles
    "cotton": "Standard textile",
    "polyester": "Standard textile",
    "elastane": "Standard textile",
    "polyamide": "Standard textile",
    "nylon": "Standard textile",
    "acrylic": "Standard textile",
    "viscose": "Standard textile",
    "modal": "Standard textile",
    "lyocell": "Standard textile",
    "tencel": "Standard textile",
    "rayon": "Standard textile",
    "hemp": "Standard textile",
    "ramie": "Standard textile",
    "spandex": "Standard textile",
    "polypropylene": "Standard textile",
    # Linen / Wool
    "linen": "Linen/Wool",
    "wool": "Linen/Wool",
    "alpaca": "Linen/Wool",
    "mohair": "Linen/Wool",
    "angora": "Linen/Wool",
    # Premium
    "cashmere": "Cashmere",
    "silk": "Silk",
    # Leather
    "leather": "Leather/Suede",
    "suede": "Leather/Suede",
    # Down
    "down": "Down",
    # Other
    "fur": "Fur",
}


def _strip_certification(material_name):
    """Strip certification suffixes from material names.

    e.g. "Cotton, Better Cotton" → "Cotton"
         "Wool, RWS Certified" → "Wool"
         "Alpaca, RAS Certified" → "Alpaca"
    """
    if "," in material_name:
        return material_name.split(",")[0].strip()
    return material_name.strip()


def map_clothing_type_v2(category, product_name=None):
    """Map T4V Product Group (category) to QFix clothing type name.

    For ambiguous categories like "Knitwear", uses product_name keywords.
    """
    if not category:
        return None

    cat_lower = category.strip().lower()

    # Direct match
    qfix_type = PRODUCT_GROUP_MAP.get(cat_lower)
    if qfix_type:
        return qfix_type

    # Ambiguous category — check product name keywords
    if cat_lower == "knitwear" and product_name:
        name_lower = product_name.lower()
        for keyword, qfix_type in PRODUCT_NAME_KEYWORDS:
            if keyword in name_lower:
                return qfix_type
        return "Knitted Jumper"  # default for knitwear

    return None


def map_material_v2(materials):
    """Map T4V materials list to QFix material category.

    materials: list of dicts with "name" and "percentage" keys.
    Returns the QFix material name based on the dominant material.
    """
    if not materials:
        return "Other/Unsure"

    # Sort by percentage descending
    sorted_mats = sorted(materials, key=lambda m: m.get("percentage", 0), reverse=True)

    for mat in sorted_mats:
        raw_name = mat.get("name", "")
        base_name = _strip_certification(raw_name).lower()
        qfix_mat = MATERIAL_MAP_EN.get(base_name)
        if qfix_mat:
            return qfix_mat

    return "Other/Unsure"


def map_product_v2(product, materials=None):
    """Map a v2 product dict to QFix IDs.

    product: dict with category, product_name, etc.
    materials: list of material dicts (or parsed from product["materials"] JSON).
    """
    import json

    if materials is None:
        raw = product.get("materials")
        if raw and isinstance(raw, str):
            try:
                materials = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                materials = []
        elif isinstance(raw, list):
            materials = raw
        else:
            materials = []

    clothing_name = map_clothing_type_v2(product.get("category"), product.get("product_name"))
    material_name = map_material_v2(materials)

    clothing_type_id = QFIX_CLOTHING_TYPE_IDS.get(clothing_name) if clothing_name else None
    material_id = _resolve_material_id(clothing_type_id, material_name)

    qfix_url = None
    if clothing_type_id and material_id:
        qfix_url = f"https://kappahl.dev.qfixr.me/sv/?category_id={clothing_type_id}&material_id={material_id}"

    return {
        "qfix_clothing_type": clothing_name,
        "qfix_clothing_type_id": clothing_type_id,
        "qfix_material": material_name,
        "qfix_material_id": material_id,
        "qfix_url": qfix_url,
    }
