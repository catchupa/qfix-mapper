"""
Maps KappAhl products to QFix repair service categories.

KappAhl hierarchy: category (dam/herr) > clothing_type > material
QFix hierarchy:    L1 (Clothing/Shoes/Bags) > L2 (Outerwear/Women's/Men's) >
                   L3 (clothing type) > L4 (material) > L5 (service type)
"""
import re

# ── QFix IDs ────────────────────────────────────────────────────────────

QFIX_CLOTHING_TYPE_IDS = {
    "Jacket": 173,
    "Unlined Jacket / Vest": 62,
    "Lined Jacket / Vest": 61,
    "Coat": 60,
    "Top / T-shirt": 90,
    "T-shirt": 163,
    "Shirt / Blouse": 89,
    "Knitted Jumper": 193,
    "Sweater": 162,
    "Sweatshirt / Hoodie": 196,
    "Midlayer": 161,
    "Trousers": 174,
    "Trousers / Shorts": 104,
    "Skirt / Dress": 66,
    "Suit": 86,
    "Swimsuit": 168,
    "Bikini": 201,
    "Swimming trunks": 169,
    "Underwear": 171,
    "Overall": 175,
    "Overalls": 160,
    "Hat": 98,
    "Cap": 99,
    "Gloves": 100,
    "Scarf / Shawl": 101,
    "Belt": 102,
    "Handbags": 123,
    "Other": 105,
}

# Valid material IDs per clothing type ID (from QFix API tree).
# Clothing and shoe categories use DIFFERENT IDs for the same material name.
# e.g. "Standard textile" = 69 for clothing, 189 for shoes.
VALID_MATERIAL_IDS = {
    60:  {69: "Standard textile", 71: "Leather/Suede", 72: "Fur", 73: "Other/Unsure"},
    61:  {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 72: "Fur", 83: "Highvis", 73: "Other/Unsure"},
    62:  {69: "Standard textile", 71: "Leather/Suede", 166: "Linen/Wool", 143: "Galloon", 83: "Highvis", 73: "Other/Unsure"},
    66:  {69: "Standard textile", 71: "Leather/Suede", 166: "Linen/Wool", 213: "Silk", 73: "Other/Unsure"},
    86:  {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 73: "Other/Unsure"},
    89:  {69: "Standard textile", 166: "Linen/Wool", 213: "Silk", 73: "Other/Unsure"},
    90:  {69: "Standard textile", 73: "Other/Unsure"},
    98:  {69: "Standard textile", 72: "Fur", 73: "Other/Unsure"},
    99:  {69: "Standard textile", 71: "Leather/Suede", 83: "Highvis", 73: "Other/Unsure"},
    100: {69: "Standard textile", 71: "Leather/Suede", 213: "Silk", 73: "Other/Unsure"},
    101: {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 72: "Fur", 213: "Silk", 73: "Other/Unsure"},
    102: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},
    104: {69: "Standard textile", 73: "Other/Unsure"},
    105: {166: "Linen/Wool", 213: "Silk", 214: "Lace", 215: "Tulle", 73: "Other/Unsure"},
    123: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},
    142: {69: "Standard textile", 83: "Highvis", 73: "Other/Unsure"},
    160: {69: "Standard textile", 176: "Down", 83: "Highvis", 144: "Flame resistant", 73: "Other/Unsure"},
    161: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},
    162: {69: "Standard textile", 73: "Other/Unsure"},
    163: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},
    168: {69: "Standard textile", 213: "Silk", 73: "Other/Unsure"},
    169: {69: "Standard textile", 213: "Silk", 73: "Other/Unsure"},
    171: {69: "Standard textile", 166: "Linen/Wool", 213: "Silk", 73: "Other/Unsure"},
    173: {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 73: "Other/Unsure"},
    174: {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 73: "Other/Unsure"},
    175: {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 83: "Highvis", 73: "Other/Unsure"},
    193: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},
    # 196 (Sweatshirt/Hoodie) and 201 (Bikini) have no materials in QFix
}

QFIX_SUBCATEGORY_IDS = {
    "Outerwear": 54,
    "Women's Clothing": 55,
    "Men's Clothing": 56,
    "Children's Clothing": 58,
    "Accessories": 57,
    "Swimwear / Wet suits": 167,
}

# ── KappAhl → QFix name mappings ────────────────────────────────────────

CLOTHING_TYPE_MAP = {
    # Outerwear
    "jackor & rockar": "Jacket",
    "jackor & kappor": "Jacket",
    "västar": "Unlined Jacket / Vest",
    "rockar": "Coat",
    "ytterplagg": "Jacket",
    "ytterkläder": "Jacket",
    # Tops
    "toppar": "Top / T-shirt",
    "toppar & t-shirts": "Top / T-shirt",
    "t-shirts & pikétröjor": "T-shirt",
    "skjortor": "Shirt / Blouse",
    "skjortor & blusar": "Shirt / Blouse",
    "blusar": "Shirt / Blouse",
    "basplagg": "Top / T-shirt",
    # Knitwear
    "tröjor & cardigans": "Knitted Jumper",
    "tröjor & koftor": "Knitted Jumper",
    # Hoodies / Sweatshirts
    "hoodies & sweatshirts": "Sweatshirt / Hoodie",
    # Bottoms
    "jeans": "Trousers",
    "byxor": "Trousers",
    "byxor & jeans": "Trousers",
    "shorts": "Trousers / Shorts",
    # Dresses & skirts
    "klänningar & kjolar": "Skirt / Dress",
    "klänningar": "Skirt / Dress",
    "kjolar": "Skirt / Dress",
    # Suits
    "kostymer": "Suit",
    "kavajer": "Suit",
    "kavajer, västar & kostymer": "Suit",
    # Swimwear
    "badkläder": "Swimsuit",
    "badkläder & uv": "Swimsuit",
    "bikini": "Bikini",
    # Underwear / socks / sleepwear
    "underkläder": "Underwear",
    "sovkläder": "Underwear",
    "pyjamas": "Underwear",
    "loungewear": "Sweatshirt / Hoodie",
    # Baby/children specific
    "bodys": "Underwear",
    "strumpor & strumpbyxor": "Underwear",
    "underställ & fleece": "Midlayer",
    "jumpsuits": "Overall",
    "träningskläder": "Sweatshirt / Hoodie",
    "mammakläder": "Trousers",
    # Shoes
    "skor & tofflor": "Sneakers",
    # Accessories
    "accessoarer": None,
    "mössor, hattar & kepsar": "Hat",
    "kepsar": "Cap",
    "vantar & handskar": "Gloves",
    "handskar & vantar": "Gloves",
    "scarves": "Scarf / Shawl",
    "halsdukar & sjalar": "Scarf / Shawl",
    "bälten": "Belt",
    "väskor & plånböcker": "Handbags",
    "solglasögon": None,
    "smycken": None,
    "håraccessoarer": None,
    "klädvård": None,
}

ACCESSORY_SUB_MAP = {
    "vantar & handskar": "Gloves",
    "handskar & vantar": "Gloves",
    "vantar": "Gloves",
    "handskar": "Gloves",
    "mössor, hattar & kepsar": "Hat",
    "mössor": "Hat",
    "hattar": "Hat",
    "kepsar": "Cap",
    "halsdukar & sjalar": "Scarf / Shawl",
    "halsdukar": "Scarf / Shawl",
    "sjalar": "Scarf / Shawl",
    "bälten": "Belt",
    "väskor & plånböcker": "Handbags",
    "väskor": "Handbags",
    "ryggsäckar": "Handbags",
}

MATERIAL_MAP = {
    # Standard textiles
    "polyester": "Standard textile",
    "återvunnen polyester": "Standard textile",
    "bomull": "Standard textile",
    "ekologisk bomull": "Standard textile",
    "återvunnen bomull": "Standard textile",
    "polyamid": "Standard textile",
    "återvunnen polyamid": "Standard textile",
    "elastan": "Standard textile",
    "viskos": "Standard textile",
    "modal": "Standard textile",
    "lyocell": "Standard textile",
    "tencel": "Standard textile",
    "akryl": "Standard textile",
    "nylon": "Standard textile",
    "regenererad nylon": "Standard textile",
    "rayon": "Standard textile",
    "hampa": "Standard textile",
    "ramie": "Standard textile",
    # Linen / Wool
    "lin": "Linen/Wool",
    "ull": "Linen/Wool",
    "certifierad ull": "Linen/Wool",
    "återvunnen ull": "Linen/Wool",
    # Premium materials
    "kashmir": "Cashmere",
    "kasjmir": "Cashmere",
    "siden": "Silk",
    "silke": "Silk",
    # Leather
    "läder": "Leather",
    "skinn": "Leather/Suede",
    "vegetabiliskt garvat": "Leather",
    # Metals (jewelry — no QFix match)
    "metall": None,
    "återvunnen metall": None,
    "mässing": None,
    "zink": None,
    "silver": None,
    "guld": None,
    "koppar": None,
    "stål": None,
}

CATEGORY_MAP = {
    "dam": "Women's Clothing",
    "herr": "Men's Clothing",
    "barn": "Children's Clothing",
    "baby": "Children's Clothing",
}


# ── Mapping functions ────────────────────────────────────────────────────

SKIP_SEGMENTS = {"dam", "herr", "barn", "baby"}


def map_clothing_type(kappahl_clothing_type):
    """Map KappAhl clothing_type string to QFix L3 clothing type name."""
    if not kappahl_clothing_type:
        return None

    parts = [p.strip().lower() for p in kappahl_clothing_type.split(">")]

    # Skip leading category segments (dam, herr, barn, baby)
    while parts and parts[0] in SKIP_SEGMENTS:
        parts = parts[1:]
    if not parts:
        return None

    first = parts[0]

    # Accessories need sub-mapping
    if first == "accessoarer" and len(parts) > 1:
        for part in parts[1:]:
            sub = ACCESSORY_SUB_MAP.get(part)
            if sub:
                return sub
        return None

    # Hoodies nested under tröjor & cardigans
    if len(parts) > 1 and "hoodies" in parts[1]:
        return "Sweatshirt / Hoodie"

    return CLOTHING_TYPE_MAP.get(first)


def map_material(kappahl_material):
    """Map KappAhl material composition to QFix L4 material category name."""
    if not kappahl_material:
        return "Other/Unsure"

    matches = re.findall(r"(\d{1,3})%\s*(.+?)(?:,|$)", kappahl_material)
    if not matches:
        return "Other/Unsure"

    sorted_mats = sorted(matches, key=lambda x: int(x[0]), reverse=True)
    for _pct, name in sorted_mats:
        name = name.strip().lower()
        qfix_mat = MATERIAL_MAP.get(name)
        if qfix_mat:
            return qfix_mat

    return "Other/Unsure"


def map_category(kappahl_category):
    """Map KappAhl category (dam/herr) to QFix L2 name."""
    return CATEGORY_MAP.get(kappahl_category, "Women's Clothing")


def _resolve_material_id(clothing_type_id, material_name):
    """Find the correct QFix material ID for a clothing type + material combo.

    Different QFix categories (clothing vs shoes) use different numeric IDs
    for the same material name, so we look up the ID from the valid combos
    for the specific clothing type.
    """
    if not clothing_type_id or not material_name:
        return None
    valid = VALID_MATERIAL_IDS.get(clothing_type_id, {})
    # Reverse lookup: find the ID whose name matches
    for mat_id, mat_name in valid.items():
        if mat_name == material_name:
            return mat_id
    # Material not available for this clothing type — fall back to Other/Unsure
    for mat_id, mat_name in valid.items():
        if mat_name == "Other/Unsure":
            return mat_id
    return None


def map_product(product):
    """Map a KappAhl product dict to QFix IDs.

    Returns dict with qfix names and numeric IDs.
    """
    clothing_name = map_clothing_type(product.get("clothing_type"))
    material_name = map_material(product.get("material_composition"))
    subcategory_name = map_category(product.get("category"))

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
        "qfix_subcategory": subcategory_name,
        "qfix_subcategory_id": QFIX_SUBCATEGORY_IDS.get(subcategory_name),
        "qfix_url": qfix_url,
    }
