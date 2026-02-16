"""Tests for QFix mapping logic."""
from mapping import (
    map_clothing_type,
    map_material,
    map_category,
    map_product,
    QFIX_CLOTHING_TYPE_IDS,
)
from mapping_v2 import (
    map_clothing_type_v2,
    map_material_v2,
    map_product_v2,
)


# ── v1 mapping (Swedish) ─────────────────────────────────────────────────

def test_map_clothing_type_jeans():
    assert map_clothing_type("Jeans") == "Trousers"


def test_map_clothing_type_nested():
    assert map_clothing_type("Dam > Jeans > Bootcut & flare") == "Trousers"


def test_map_clothing_type_skjortor():
    assert map_clothing_type("Skjortor & blusar") == "Shirt / Blouse"


def test_map_clothing_type_none():
    assert map_clothing_type(None) is None


def test_map_clothing_type_unknown():
    assert map_clothing_type("nonexistent category") is None


def test_map_clothing_type_accessories():
    assert map_clothing_type("Accessoarer > Vantar & handskar") == "Gloves"


def test_map_material_bomull():
    assert map_material("75% Bomull, 21% Polyester, 4% Elastan") == "Standard textile"


def test_map_material_ull():
    assert map_material("80% Ull, 20% Polyamid") == "Linen/Wool"


def test_map_material_kashmir():
    assert map_material("100% Kashmir") == "Cashmere"


def test_map_material_none():
    assert map_material(None) == "Other/Unsure"


def test_map_material_empty():
    assert map_material("") == "Other/Unsure"


def test_map_category_dam():
    assert map_category("dam") == "Women's Clothing"


def test_map_category_herr():
    assert map_category("herr") == "Men's Clothing"


def test_map_category_barn():
    assert map_category("barn") == "Children's Clothing"


def test_map_product_full():
    product = {
        "category": "dam",
        "clothing_type": "Jeans",
        "material_composition": "98% Bomull, 2% Elastan",
    }
    result = map_product(product)
    assert result["qfix_clothing_type"] == "Trousers"
    assert result["qfix_clothing_type_id"] == QFIX_CLOTHING_TYPE_IDS["Trousers"]
    assert result["qfix_material"] == "Standard textile"
    assert result["qfix_material_id"] is not None
    assert result["qfix_subcategory"] == "Women's Clothing"
    assert result["qfix_url"] is not None


def test_map_product_missing_fields():
    result = map_product({})
    assert result["qfix_clothing_type"] is None
    assert result["qfix_clothing_type_id"] is None
    assert result["qfix_url"] is None


# ── v2 mapping (English) ─────────────────────────────────────────────────

def test_map_clothing_type_v2_denim():
    assert map_clothing_type_v2("Denim") == "Trousers"


def test_map_clothing_type_v2_knitwear_skirt():
    assert map_clothing_type_v2("Knitwear", "Wide knitted skirt") == "Skirt / Dress"


def test_map_clothing_type_v2_knitwear_default():
    # With a product name that doesn't match any keyword, defaults to Knitted Jumper
    assert map_clothing_type_v2("Knitwear", "Some knitted thing") == "Knitted Jumper"


def test_map_clothing_type_v2_none():
    assert map_clothing_type_v2(None) is None


def test_map_material_v2_cotton():
    materials = [{"name": "Cotton, Better Cotton", "percentage": 0.98}]
    assert map_material_v2(materials) == "Standard textile"


def test_map_material_v2_wool():
    materials = [{"name": "Wool, RWS Certified", "percentage": 0.80}]
    assert map_material_v2(materials) == "Linen/Wool"


def test_map_material_v2_empty():
    assert map_material_v2([]) == "Other/Unsure"
    assert map_material_v2(None) == "Other/Unsure"


def test_map_product_v2_full():
    product = {
        "category": "Denim",
        "product_name": "Front seam flare jeans",
        "materials": '[{"name": "Cotton, Better Cotton", "percentage": 0.98}, {"name": "Elastane", "percentage": 0.02}]',
    }
    result = map_product_v2(product)
    assert result["qfix_clothing_type"] == "Trousers"
    assert result["qfix_material"] == "Standard textile"
    assert result["qfix_url"] is not None
