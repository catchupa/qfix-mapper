"""Tests for QFixCatalog — service filtering and variant swapping."""
import pytest
from catalog import QFixCatalog


@pytest.fixture
def cat():
    """A QFixCatalog pre-loaded with test data (no HTTP calls)."""
    c = QFixCatalog()
    # Simulate loaded state
    c._loaded = True
    c.items = {
        93: {"id": 93, "name": "Jacket", "slug": "jacket", "link": None, "description": None,
             "parent": {"id": 10, "name": "Men's Clothing", "slug": "mens", "link": None, "description": None}},
    }
    c.subitems = {
        69: {"id": 69, "name": "Standard textile", "slug": "standard-textile", "link": None, "description": None},
    }
    c.services = {
        (93, 69): [
            {
                "id": 37, "name": "Repair", "slug": "service-category-clothing-repair",
                "services": [
                    {"id": 1395, "name": "Replace main zipper", "price": 199, "variants": []},
                    {"id": 1401, "name": "Replace main zipper", "price": 299, "variants": []},
                    {"id": 920, "name": "Repair tear", "price": 434, "variants": []},
                    {"id": 1420, "name": "Repair tear", "price": 269, "variants": []},
                ],
            },
            {
                "id": 42, "name": "Washing", "slug": "service-category-clothing-washing",
                "services": [
                    {"id": 1323, "name": "Dry Cleaning", "price": 399, "variants": []},
                    {"id": 1349, "name": "Waterwash", "price": 99, "variants": []},
                ],
            },
        ],
    }
    # 1395 is valid for ct_id=93, 1401 is NOT
    # 920 is valid for ct_id=93, 1420 is NOT
    c.assigned_categories = {
        1395: {93, 85},
        1401: {85},       # only valid for Women's Jacket (85), not Men's (93)
        920: {93, 85},
        1420: {85},        # only Women's
        1323: {93, 85},
        1349: {93},
    }
    return c


class TestSwapToValidVariants:
    def test_swaps_invalid_to_valid_variant(self, cat):
        actions = [
            {"id": 1401, "name": "Replace main zipper", "price": 299},
            {"id": 920, "name": "Repair tear", "price": 434},
        ]
        result = cat.swap_to_valid_variants(actions, ct_id=93, mat_id=69, service_key="repair")
        # 1401 should be swapped to 1395 (valid for ct_id=93, cheaper)
        assert result[0]["id"] == 1395
        assert result[0]["price"] == 199
        # 920 is already valid, should stay
        assert result[1]["id"] == 920

    def test_keeps_valid_variant_unchanged(self, cat):
        actions = [{"id": 1395, "name": "Replace main zipper", "price": 199}]
        result = cat.swap_to_valid_variants(actions, ct_id=93, mat_id=69, service_key="repair")
        assert result[0]["id"] == 1395

    def test_keeps_unknown_action_unchanged(self, cat):
        actions = [{"id": 9999, "name": "Unknown service", "price": 100}]
        result = cat.swap_to_valid_variants(actions, ct_id=93, mat_id=69, service_key="repair")
        assert result[0]["id"] == 9999

    def test_empty_actions(self, cat):
        assert cat.swap_to_valid_variants([], ct_id=93, mat_id=69, service_key="repair") == []

    def test_no_assigned_categories(self):
        c = QFixCatalog()
        c._loaded = True
        actions = [{"id": 1401, "name": "Replace main zipper", "price": 299}]
        result = c.swap_to_valid_variants(actions, ct_id=93, mat_id=69, service_key="repair")
        assert result[0]["id"] == 1401  # No swap when no assigned_categories data


class TestFilterByAssignedCategories:
    def test_filters_invalid_actions(self, cat):
        actions = [
            {"id": 1395, "name": "Replace main zipper", "price": 199},
            {"id": 1401, "name": "Replace main zipper", "price": 299},
            {"id": 920, "name": "Repair tear", "price": 434},
        ]
        result = cat.filter_by_assigned_categories(actions, ct_id=93, mat_id=69, service_key="repair")
        ids = [a["id"] for a in result]
        assert 1395 in ids
        assert 920 in ids
        assert 1401 not in ids

    def test_backfills_when_too_few(self, cat):
        actions = [{"id": 1395, "name": "Replace main zipper", "price": 199}]
        result = cat.filter_by_assigned_categories(
            actions, ct_id=93, mat_id=69, service_key="repair", max_actions=3
        )
        assert len(result) >= 2  # Should backfill with 920 from catalog
        ids = [a["id"] for a in result]
        assert 1395 in ids
        assert 920 in ids

    def test_no_assigned_categories_passes_through(self):
        c = QFixCatalog()
        c._loaded = True
        actions = [{"id": 1401, "name": "Test", "price": 100}]
        result = c.filter_by_assigned_categories(actions, ct_id=93, mat_id=69, service_key="repair")
        assert result == actions


class TestFilterServices:
    def test_off_mode_passes_through(self):
        c = QFixCatalog()
        c.filter_mode = "off"
        actions = [{"id": 1, "name": "Test"}]
        assert c.filter_services(actions, 93, 69, "repair") == actions

    def test_assigned_categories_mode(self, cat):
        cat.filter_mode = "assigned_categories"
        actions = [
            {"id": 1395, "name": "Replace main zipper", "price": 199},
            {"id": 1401, "name": "Replace main zipper", "price": 299},
        ]
        result = cat.filter_services(actions, 93, 69, "repair")
        assert len(result) >= 1
        assert all(a["id"] != 1401 for a in result)


class TestEnrichQfix:
    def test_adds_item_and_subitem(self, cat):
        qfix = {"qfix_clothing_type_id": 93, "qfix_material_id": 69}
        result = cat.enrich_qfix(qfix)
        assert result["qfix_item"]["name"] == "Jacket"
        assert result["qfix_item"]["parent"]["name"] == "Men's Clothing"
        assert result["qfix_subitem"]["name"] == "Standard textile"
        assert len(result["qfix_services"]) == 2

    def test_missing_ids_no_crash(self, cat):
        qfix = {"qfix_clothing_type_id": None, "qfix_material_id": None}
        result = cat.enrich_qfix(qfix)
        assert "qfix_item" not in result
