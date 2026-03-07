"""Tests for brands module."""
from brands import (
    BRAND_ROUTES, BRAND_SLUG, ALL_BRANDS,
    slug_for_brand, brand_for_slug,
)


def test_brand_routes_contains_all_brands():
    assert "kappahl" in BRAND_ROUTES
    assert "ginatricot" in BRAND_ROUTES
    assert "eton" in BRAND_ROUTES
    assert "nudie" in BRAND_ROUTES
    assert "lindex" in BRAND_ROUTES


def test_brand_slug_is_reverse_of_routes():
    for slug, name in BRAND_ROUTES.items():
        assert BRAND_SLUG[name] == slug


def test_all_brands_sorted():
    assert ALL_BRANDS == sorted(ALL_BRANDS)
    assert len(ALL_BRANDS) == len(BRAND_ROUTES)


def test_slug_for_brand_exact():
    assert slug_for_brand("KappAhl") == "kappahl"
    assert slug_for_brand("Gina Tricot") == "ginatricot"
    assert slug_for_brand("Nudie Jeans") == "nudie"
    assert slug_for_brand("Eton") == "eton"
    assert slug_for_brand("Lindex") == "lindex"


def test_brand_for_slug():
    assert brand_for_slug("kappahl") == "KappAhl"
    assert brand_for_slug("nudie") == "Nudie Jeans"
    assert brand_for_slug("unknown") is None
