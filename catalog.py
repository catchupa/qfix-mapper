"""QFix catalog loading and service filtering.

Encapsulates the QFix category tree, service lookups, and filtering logic
that was previously spread across module-level globals in api.py.
"""

import json
import logging
import os

import requests as http_requests

logger = logging.getLogger(__name__)

QFIX_CATEGORIES_URL = "https://dev.qfixr.me/wp-json/qfix/v1/product-categories?parent=23"

# Service key -> slug fragment mapping (used for matching L5 categories)
_SLUG_MAP = {"repair": "repair", "adjustment": "adjustment", "care": "washing"}


class QFixCatalog:
    """QFix category tree and service filtering.

    Loads the catalog from the QFix API on first call to load(),
    then provides filtering and enrichment methods.
    """

    def __init__(self):
        self.items = {}            # L3 clothing types: {id: {name, slug, link, parent}}
        self.subitems = {}         # L4 materials: {id: {name, slug, link}}
        self.services = {}         # {(L3_id, L4_id): [service_categories]}
        self.assigned_categories = {}  # {action_id: set(L3 category IDs)}
        self._loaded = False

        # Legacy allowlist filter
        self._allowed_services = {}  # {ct_id_str: {mat_id_str: {svc_key: [{id, name}]}}}

        # Filter strategy from env
        self.filter_mode = os.environ.get("QFIX_SERVICE_FILTER", "assigned_categories")
        if os.environ.get("QFIX_FILTER_SERVICES") == "0":
            self.filter_mode = "off"

    @property
    def loaded(self):
        return self._loaded

    def load(self):
        """Fetch the QFix category tree and build lookup dicts. Idempotent."""
        if self._loaded:
            return
        try:
            resp = http_requests.get(QFIX_CATEGORIES_URL, timeout=30)
            resp.raise_for_status()
            tree = resp.json()
        except Exception as e:
            logger.warning("Failed to fetch QFix catalog: %s", e)
            return

        for l1 in tree:
            for l2 in l1.get("children", []):
                for l3 in l2.get("children", []):
                    l3_id = l3.get("id")
                    if l3_id not in self.items:
                        self.items[l3_id] = {
                            **_build_catalog_node(l3),
                            "parent": _build_catalog_node(l2),
                        }
                    for l4 in l3.get("children", []):
                        l4_id = l4.get("id")
                        if l4_id not in self.subitems:
                            self.subitems[l4_id] = _build_catalog_node(l4)

                        service_categories = []
                        for l5 in l4.get("children", []):
                            svc_cat = {
                                "id": l5.get("id"),
                                "name": l5.get("name"),
                                "slug": l5.get("slug"),
                                "services": [],
                            }
                            for prod in l5.get("products", []):
                                service = {
                                    "id": prod.get("id"),
                                    "name": prod.get("name"),
                                    "price": prod.get("price"),
                                    "variants": [
                                        {
                                            "id": v.get("id"),
                                            "name": v.get("name"),
                                            "price": v.get("price"),
                                        }
                                        for v in prod.get("variants", [])
                                    ],
                                }
                                svc_cat["services"].append(service)
                                ac = prod.get("assigned_categories", "")
                                if ac and prod["id"] not in self.assigned_categories:
                                    self.assigned_categories[prod["id"]] = set(
                                        int(c) for c in ac.split(",") if c.strip()
                                    )
                            service_categories.append(svc_cat)
                        self.services[(l3_id, l4_id)] = service_categories

        self._loaded = True
        logger.info(
            "QFix catalog loaded: %d items, %d subitems, %d service combos, %d actions with assigned_categories",
            len(self.items), len(self.subitems), len(self.services), len(self.assigned_categories),
        )

    def _load_allowed_services(self):
        """Load the legacy allowlist from JSON file."""
        if self._allowed_services:
            return
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qfix_services_by_type.json")
        if os.path.exists(path):
            with open(path) as f:
                self._allowed_services = json.load(f)
            logger.info("Loaded QFix service allowlist: %d clothing types", len(self._allowed_services))

    def enrich_qfix(self, qfix):
        """Add catalog item, subitem, and service data to a qfix mapping dict."""
        self.load()
        ct_id = qfix.get("qfix_clothing_type_id")
        mat_id = qfix.get("qfix_material_id")
        if ct_id and ct_id in self.items:
            qfix["qfix_item"] = self.items[ct_id]
        if mat_id and mat_id in self.subitems:
            qfix["qfix_subitem"] = self.subitems[mat_id]
        if ct_id and mat_id:
            qfix["qfix_services"] = self.services.get((ct_id, mat_id), [])
        return qfix

    def swap_to_valid_variants(self, actions, ct_id, mat_id, service_key):
        """Swap action variants to prefer ones valid for this clothing type.

        When the AI ranking picks e.g. "Replace main zipper" #1401 but that ID
        isn't in assigned_categories for this ct_id, look for another variant
        with the same name (e.g. #1395) that IS valid, and swap it in.
        """
        if not self.assigned_categories:
            return actions

        slug_pattern = _SLUG_MAP.get(service_key, service_key)
        svc_cats = self.services.get((ct_id, mat_id), [])

        name_to_valid = {}
        for svc_cat in svc_cats:
            if slug_pattern not in svc_cat.get("slug", ""):
                continue
            for s in svc_cat.get("services", []):
                if ct_id in self.assigned_categories.get(s["id"], set()):
                    name_to_valid.setdefault(s["name"], []).append(s)

        result = []
        for a in actions:
            aid = a.get("id")
            if ct_id in self.assigned_categories.get(aid, set()):
                result.append(a)
                continue
            variants = name_to_valid.get(a.get("name"), [])
            if variants:
                best = min(variants, key=lambda v: v.get("price") or 9999)
                result.append({"id": best["id"], "name": best["name"], "price": best.get("price")})
            else:
                result.append(a)
        return result

    def filter_by_assigned_categories(self, actions, ct_id, mat_id, service_key, max_actions=5):
        """Filter actions by assigned_categories, backfilling if needed."""
        if not self.assigned_categories:
            return actions

        filtered = [a for a in actions
                    if ct_id in self.assigned_categories.get(a.get("id"), set())]

        if len(filtered) < max_actions:
            seen_ids = {a["id"] for a in filtered}
            slug_pattern = _SLUG_MAP.get(service_key, service_key)

            svc_cats = self.services.get((ct_id, mat_id), [])
            for svc_cat in svc_cats:
                if slug_pattern not in svc_cat.get("slug", ""):
                    continue
                for s in svc_cat.get("services", []):
                    if s["id"] in seen_ids:
                        continue
                    if ct_id not in self.assigned_categories.get(s["id"], set()):
                        continue
                    filtered.append({"id": s["id"], "name": s["name"], "price": s.get("price")})
                    seen_ids.add(s["id"])
                    if len(filtered) >= max_actions:
                        break
                break

        return filtered

    def filter_allowed_services(self, actions, ct_id, mat_id, service_key):
        """Legacy allowlist filter."""
        self._load_allowed_services()
        if not self._allowed_services:
            return actions
        allowed = self._allowed_services.get(str(ct_id), {}).get(str(mat_id), {}).get(service_key)
        if allowed is None:
            return actions
        allowed_ids = {s["id"] for s in allowed}
        return [a for a in actions if a.get("id") in allowed_ids]

    def filter_services(self, actions, ct_id, mat_id, service_key):
        """Apply the active service filter strategy."""
        if self.filter_mode == "off":
            return actions
        if self.filter_mode == "allowlist":
            return self.filter_allowed_services(actions, ct_id, mat_id, service_key)
        self.load()
        return self.filter_by_assigned_categories(actions, ct_id, mat_id, service_key)


def _build_catalog_node(node):
    """Extract the fields we want from a QFix catalog node."""
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "slug": node.get("slug"),
        "link": node.get("link"),
        "description": node.get("category_description") or None,
    }


# Module-level singleton
catalog = QFixCatalog()
