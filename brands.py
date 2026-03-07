"""Centralized brand configuration.

Single source of truth for brand slug <-> display name mappings.
"""

# slug -> display name (used in URL routes)
BRAND_ROUTES = {
    "kappahl": "KappAhl",
    "ginatricot": "Gina Tricot",
    "eton": "Eton",
    "nudie": "Nudie Jeans",
    "lindex": "Lindex",
}

# display name -> slug (reverse lookup)
BRAND_SLUG = {v: k for k, v in BRAND_ROUTES.items()}

# All display names, sorted
ALL_BRANDS = sorted(BRAND_ROUTES.values())


def slug_for_brand(display_name):
    """Convert a brand display name to its URL slug.

    Handles exact matches first, then falls back to normalizing
    (lowercasing and removing spaces).

    >>> slug_for_brand("KappAhl")
    'kappahl'
    >>> slug_for_brand("Nudie Jeans")
    'nudie'
    """
    if display_name in BRAND_SLUG:
        return BRAND_SLUG[display_name]
    # Fallback: normalize and check
    normalized = display_name.lower().replace(" ", "")
    for slug in BRAND_ROUTES:
        if slug == normalized:
            return slug
    return normalized


def brand_for_slug(slug):
    """Convert a URL slug to its display name, or None if unknown."""
    return BRAND_ROUTES.get(slug)
