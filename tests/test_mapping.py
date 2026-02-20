"""Tests for QFix mapping logic."""
import pytest
from mapping import (
    map_clothing_type,
    map_material,
    map_category,
    map_product,
    map_product_legacy,
    QFIX_CLOTHING_TYPE_IDS,
    QFIX_CLOTHING_TYPE_IDS_LEGACY,
    VALID_MATERIAL_IDS,
    VALID_MATERIAL_IDS_LEGACY,
    QFIX_SUBCATEGORY_IDS,
    QFIX_SUBCATEGORY_IDS_LEGACY,
    BRAND_CLOTHING_TYPE_OVERRIDES,
    BRAND_KEYWORD_CLOTHING_OVERRIDES,
    BRAND_MATERIAL_OVERRIDES,
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


def test_map_material_space_separated():
    assert map_material("98% Cotton 2% Elastane") == "Standard textile"


def test_map_material_space_separated_wool():
    assert map_material("70% Wool 25% Polyamide 5% Other Fibre") == "Linen/Wool"


def test_map_material_space_separated_silk():
    assert map_material("92% Silk 8% Polyamide") == "Silk"


def test_map_material_reversed_format():
    assert map_material("Cotton 100%") == "Standard textile"


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


# ── Legacy vs New mapping comparison ────────────────────────────────────

def test_new_clothing_types_superset_of_legacy():
    """Every clothing type name in legacy must also exist in the new mapping."""
    legacy_names = set(QFIX_CLOTHING_TYPE_IDS_LEGACY.keys())
    new_names = set(QFIX_CLOTHING_TYPE_IDS.keys())
    missing = legacy_names - new_names
    assert missing == set(), f"Legacy types missing from new mapping: {missing}"


def test_new_has_more_clothing_types():
    """New mapping should have strictly more clothing types than legacy."""
    assert len(QFIX_CLOTHING_TYPE_IDS) > len(QFIX_CLOTHING_TYPE_IDS_LEGACY)


def test_new_subcategories_superset_of_legacy():
    """Every subcategory in legacy must also exist in the new mapping."""
    legacy_names = set(QFIX_SUBCATEGORY_IDS_LEGACY.keys())
    new_names = set(QFIX_SUBCATEGORY_IDS.keys())
    missing = legacy_names - new_names
    assert missing == set(), f"Legacy subcategories missing from new mapping: {missing}"


def test_new_has_more_subcategories():
    """New mapping should have strictly more subcategories than legacy."""
    assert len(QFIX_SUBCATEGORY_IDS) > len(QFIX_SUBCATEGORY_IDS_LEGACY)


def test_new_materials_superset_of_legacy():
    """Every clothing type ID in legacy materials must exist in new materials."""
    legacy_ids = set(VALID_MATERIAL_IDS_LEGACY.keys())
    new_ids = set(VALID_MATERIAL_IDS.keys())
    missing = legacy_ids - new_ids
    assert missing == set(), f"Legacy material clothing type IDs missing from new: {missing}"


def test_new_has_more_material_entries():
    """New mapping should cover more clothing type IDs for materials."""
    assert len(VALID_MATERIAL_IDS) > len(VALID_MATERIAL_IDS_LEGACY)


def test_legacy_mapping_results_valid_in_new():
    """Products mapped by legacy should also map successfully with new mapping."""
    sample_products = [
        {"category": "dam", "clothing_type": "Jeans", "material_composition": "98% Bomull, 2% Elastan"},
        {"category": "herr", "clothing_type": "Skjortor & blusar", "material_composition": "100% Bomull"},
        {"category": "barn", "clothing_type": "Tröjor & cardigans", "material_composition": "80% Ull, 20% Polyamid"},
        {"category": "dam", "clothing_type": "Klänningar & kjolar", "material_composition": "100% Viskos"},
        {"category": "herr", "clothing_type": "Kostymer", "material_composition": "50% Ull, 50% Polyester"},
    ]
    for product in sample_products:
        legacy_result = map_product_legacy(product)
        new_result = map_product(product)
        # If legacy resolved a clothing type, new should too
        if legacy_result["qfix_clothing_type"]:
            assert new_result["qfix_clothing_type"] == legacy_result["qfix_clothing_type"], (
                f"Clothing type mismatch for {product}: legacy={legacy_result['qfix_clothing_type']}, new={new_result['qfix_clothing_type']}"
            )
        # If legacy resolved a URL, new should too
        if legacy_result["qfix_url"]:
            assert new_result["qfix_url"] is not None, (
                f"New mapping lost URL for {product}"
            )


def test_new_mapping_covers_shoes():
    """New mapping should include shoe types that legacy lacks."""
    shoe_types = ["Sneakers", "Boots", "Rain boots", "Sandals", "Winter boots"]
    for shoe in shoe_types:
        assert shoe in QFIX_CLOTHING_TYPE_IDS, f"{shoe} missing from new mapping"


def test_new_mapping_covers_workwear():
    """New mapping should include workwear subcategory."""
    assert "Workwear" in QFIX_SUBCATEGORY_IDS
    assert "Workwear" not in QFIX_SUBCATEGORY_IDS_LEGACY


def test_new_mapping_covers_additional_outerwear():
    """New mapping includes additional outerwear types."""
    extra_types = ["Rain Jacket", "Rain Trousers", "Ski / Shell jacket", "Ski / Shell Trousers"]
    for t in extra_types:
        assert t in QFIX_CLOTHING_TYPE_IDS, f"{t} missing from new mapping"


# ── Brand-specific overrides ──────────────────────────────────────────────

@pytest.fixture(autouse=False)
def clean_brand_overrides():
    """Save and restore brand override dicts around tests."""
    saved_ct = dict(BRAND_CLOTHING_TYPE_OVERRIDES)
    saved_kw = dict(BRAND_KEYWORD_CLOTHING_OVERRIDES)
    saved_mat = dict(BRAND_MATERIAL_OVERRIDES)
    BRAND_CLOTHING_TYPE_OVERRIDES.clear()
    BRAND_KEYWORD_CLOTHING_OVERRIDES.clear()
    BRAND_MATERIAL_OVERRIDES.clear()
    yield
    BRAND_CLOTHING_TYPE_OVERRIDES.clear()
    BRAND_CLOTHING_TYPE_OVERRIDES.update(saved_ct)
    BRAND_KEYWORD_CLOTHING_OVERRIDES.clear()
    BRAND_KEYWORD_CLOTHING_OVERRIDES.update(saved_kw)
    BRAND_MATERIAL_OVERRIDES.clear()
    BRAND_MATERIAL_OVERRIDES.update(saved_mat)


def test_brand_clothing_type_override_takes_priority(clean_brand_overrides):
    """Brand override should override global map for that brand."""
    BRAND_CLOTHING_TYPE_OVERRIDES["eton"] = {"skjortor": "Shirt / Blouse"}
    # "skjortor" globally maps to "Top / T-shirt" (or similar), but for eton it should be "Shirt / Blouse"
    result = map_clothing_type("Skjortor", brand="eton")
    assert result == "Shirt / Blouse"


def test_brand_clothing_type_override_does_not_affect_other_brands(clean_brand_overrides):
    """Brand override for one brand should not affect another brand."""
    BRAND_CLOTHING_TYPE_OVERRIDES["eton"] = {"skjortor": "Shirt / Blouse"}
    # Without brand, should use global map
    result_global = map_clothing_type("Skjortor")
    result_kappahl = map_clothing_type("Skjortor", brand="kappahl")
    # Both should return the same (global) result, not the eton override
    assert result_global == result_kappahl


def test_brand_clothing_type_fallback_to_global(clean_brand_overrides):
    """When no brand override exists, should fall back to global map."""
    result = map_clothing_type("Jeans", brand="eton")
    assert result == "Trousers"


def test_brand_keyword_clothing_override(clean_brand_overrides):
    """Brand keyword override should match before global keywords."""
    BRAND_KEYWORD_CLOTHING_OVERRIDES["nudie"] = [("special_thing", "Trousers")]
    result = map_clothing_type("Some > special_thing > category", brand="nudie")
    assert result == "Trousers"
    # Without brand, should not match
    result_global = map_clothing_type("Some > special_thing > category")
    assert result_global != "Trousers" or result_global is None


def test_brand_material_override(clean_brand_overrides):
    """Brand material override should take priority over global map."""
    BRAND_MATERIAL_OVERRIDES["ginatricot"] = {"bomull": "Linen/Wool"}
    result = map_material("100% Bomull", brand="ginatricot")
    assert result == "Linen/Wool"
    # Without brand, bomull maps to Standard textile globally
    result_global = map_material("100% Bomull")
    assert result_global == "Standard textile"


def test_brand_material_override_bare_name(clean_brand_overrides):
    """Brand material override should work for bare material names."""
    BRAND_MATERIAL_OVERRIDES["eton"] = {"silke": "Silk"}
    result = map_material("Silke", brand="eton")
    assert result == "Silk"


def test_map_product_with_brand(clean_brand_overrides):
    """map_product should pass brand through to sub-mappers."""
    BRAND_CLOTHING_TYPE_OVERRIDES["lindex"] = {"klänningar": "Skirt / Dress"}
    product = {
        "clothing_type": "Klänningar",
        "material_composition": "100% Bomull",
        "category": "dam",
    }
    result = map_product(product, brand="lindex")
    assert result["qfix_clothing_type"] == "Skirt / Dress"
