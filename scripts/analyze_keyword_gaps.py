"""Analyze keyword injection gaps for KappAhl products.

Finds products where keyword rules would inject repair/care actions,
but those actions are filtered out by QFix assigned_categories.
These are gaps we should raise with QFix to fix in their catalog.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor
from catalog import catalog
from database import DATABASE_URL

KEYWORD_ACTION_RULES = [
    {
        "keywords": ["dragkedja", "zipper", "blixtlås", "zip"],
        "actions": [
            {"name": "Replace zipper", "default": True},
            {"name": "Replace main zipper", "default": True},
            {"name": "Replace zipper slider"},
        ],
        "category": "repair",
    },
    {
        "keywords": ["knapp", "knappar", "button", "buttons"],
        "actions": [
            {"name": "Replace button", "default": True},
            {"name": "Replace snap button"},
            {"name": "Replace jeans button"},
        ],
        "category": "repair",
    },
    {
        "keywords": ["spänne", "buckle"],
        "actions": [{"name": "Replace buckle", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["foder", "lining", "fodrad"],
        "actions": [
            {"name": "Replace lining", "default": True},
        ],
        "category": "repair",
    },
    {
        "keywords": ["resår", "elastic", "elastisk"],
        "actions": [{"name": "Replace elastic", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["kardborre", "velcro"],
        "actions": [{"name": "Replace velcro", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["reflex", "reflexer", "reflective"],
        "actions": [{"name": "Replace reflectors", "default": True}],
        "category": "repair",
    },
    {
        "keywords": ["läder", "leather", "skinn", "mocka", "suede", "nubuck"],
        "actions": [{"name": "Clean and condition", "default": True}],
        "category": "care",
    },
    {
        "keywords": ["dun", "dunfyllning", "down filled", "down jacket"],
        "actions": [{"name": "Dry cleaning", "default": True}],
        "category": "care",
    },
    {
        "keywords": ["impregnera", "waterproof", "vattentät", "gore-tex", "shell"],
        "actions": [{"name": "Waterproofing", "default": True}],
        "category": "care",
    },
]


def find_action_in_catalog(action_name, ct_id, mat_id, category):
    """Find an action by name in the catalog for a given clothing type + material."""
    slug_map = {"repair": "repair", "adjustment": "adjustment", "care": "washing"}
    slug_pattern = slug_map.get(category, category)

    svc_cats = catalog.services.get((ct_id, mat_id), [])
    for svc_cat in svc_cats:
        if slug_pattern not in svc_cat.get("slug", ""):
            continue
        for s in svc_cat.get("services", []):
            if s["name"] == action_name:
                return s
    return None


def check_action_valid(action_id, ct_id):
    """Check if an action is valid for a clothing type via assigned_categories."""
    return ct_id in catalog.assigned_categories.get(action_id, set())


def analyze_brand(brand_name="KappAhl"):
    catalog.load()

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT product_id, product_name, description, clothing_type,
                   qfix_clothing_type, qfix_clothing_type_id,
                   qfix_material, qfix_material_id
            FROM products_unified
            WHERE brand = %s AND qfix_clothing_type_id IS NOT NULL
        """, (brand_name,))
        products = cur.fetchall()
    conn.close()

    # {(ct_id, action_name, rule_keywords): {products: [...], action_id, ...}}
    gaps = {}

    for product in products:
        ct_id = product["qfix_clothing_type_id"]
        mat_id = product["qfix_material_id"]
        product_text = " ".join(filter(None, [
            product.get("product_name", ""),
            product.get("description", ""),
            product.get("clothing_type", ""),
        ])).lower()

        for rule in KEYWORD_ACTION_RULES:
            # Check if any keyword matches
            matched_keywords = [kw for kw in rule["keywords"] if kw in product_text]
            if not matched_keywords:
                continue

            # Check each action in the rule
            for action_spec in rule["actions"]:
                action_name = action_spec["name"]

                # Check sub_keywords if present
                if "sub_keywords" in action_spec and not action_spec.get("default"):
                    if not any(sk in product_text for sk in action_spec["sub_keywords"]):
                        continue

                # Find the action in the catalog
                action = find_action_in_catalog(action_name, ct_id, mat_id, rule["category"])
                if not action:
                    continue  # Action doesn't exist for this combo at all

                action_id = action["id"]
                is_valid = check_action_valid(action_id, ct_id)

                if is_valid:
                    continue  # No gap — action is valid

                # GAP FOUND: keyword matches but action is blocked
                ct_name = catalog.items.get(ct_id, {}).get("name", f"ID {ct_id}")
                ct_parent = catalog.items.get(ct_id, {}).get("parent", {}).get("name", "?")
                gap_key = (ct_id, action_name, action_id)

                if gap_key not in gaps:
                    gaps[gap_key] = {
                        "action_name": action_name,
                        "action_id": action_id,
                        "action_price": action.get("price"),
                        "ct_id": ct_id,
                        "ct_name": ct_name,
                        "ct_parent": ct_parent,
                        "mat_id": mat_id,
                        "category": rule["category"],
                        "triggered_by_keywords": list(rule["keywords"]),
                        "products": [],
                    }

                gaps[gap_key]["products"].append({
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "matched_keywords": matched_keywords,
                })

    return gaps


def main():
    print("Analyzing keyword injection gaps for KappAhl...\n")
    gaps = analyze_brand("KappAhl")

    if not gaps:
        print("No gaps found!")
        return

    # Group by clothing type for readability
    by_ct = {}
    for gap_key, gap in sorted(gaps.items(), key=lambda x: (-len(x[1]["products"]), x[1]["ct_name"])):
        ct_id = gap["ct_id"]
        if ct_id not in by_ct:
            by_ct[ct_id] = {
                "ct_name": gap["ct_name"],
                "ct_parent": gap["ct_parent"],
                "ct_id": ct_id,
                "gaps": [],
            }
        by_ct[ct_id]["gaps"].append(gap)

    total_products_affected = 0
    total_gaps = 0

    print("=" * 80)
    print("KEYWORD INJECTION GAPS — KappAhl")
    print("Actions triggered by keywords but blocked by assigned_categories")
    print("=" * 80)

    for ct_id, ct_group in sorted(by_ct.items(), key=lambda x: x[1]["ct_name"]):
        print(f"\n{'─' * 70}")
        print(f"  {ct_group['ct_name']} (ID {ct_id}) — {ct_group['ct_parent']}")
        print(f"{'─' * 70}")

        for gap in ct_group["gaps"]:
            n = len(gap["products"])
            total_products_affected += n
            total_gaps += 1
            print(f"\n  ✗ {gap['action_name']} (ID {gap['action_id']}, {gap['action_price']} kr)")
            print(f"    Category: {gap['category']}")
            print(f"    Keywords: {', '.join(gap['triggered_by_keywords'])}")
            print(f"    Products affected: {n}")
            # Show up to 3 example products
            for p in gap["products"][:3]:
                kws = ", ".join(p["matched_keywords"])
                print(f"      - {p['product_id']}: {p['product_name']} [matched: {kws}]")
            if n > 3:
                print(f"      ... and {n - 3} more")

    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {total_gaps} blocked actions across {len(by_ct)} clothing types")
    print(f"         {total_products_affected} total product×action combinations affected")
    print(f"{'=' * 80}")

    # Output JSON for the gap page
    output = {
        "brand": "KappAhl",
        "total_gaps": total_gaps,
        "total_product_action_combos": total_products_affected,
        "clothing_types_affected": len(by_ct),
        "gaps": [],
    }

    for ct_id, ct_group in sorted(by_ct.items(), key=lambda x: x[1]["ct_name"]):
        for gap in ct_group["gaps"]:
            output["gaps"].append({
                "action_name": gap["action_name"],
                "action_id": gap["action_id"],
                "action_price": gap["action_price"],
                "category": gap["category"],
                "ct_id": gap["ct_id"],
                "ct_name": gap["ct_name"],
                "ct_parent": gap["ct_parent"],
                "keywords": gap["triggered_by_keywords"],
                "product_count": len(gap["products"]),
                "example_products": [
                    {"id": p["product_id"], "name": p["product_name"], "matched": p["matched_keywords"]}
                    for p in gap["products"][:5]
                ],
            })

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "keyword_gaps_kappahl.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nJSON output written to {out_path}")


if __name__ == "__main__":
    main()
