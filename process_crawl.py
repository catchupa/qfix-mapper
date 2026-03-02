#!/usr/bin/env python3
"""
Process crawled QFix service data:
1. Map Swedish service names to English names + QFix product IDs
2. Match crawled L2/L3/L4 to QFix clothing_type_id and material_id
3. Output qfix_services_by_type.json keyed by ct_id → mat_id → service_category → [services]
"""

import json

# Swedish → English service name mapping (from crawl → API)
SV_TO_EN = {
    # Repair
    "Byt dragkedja": "Replace zipper",
    "Byt löpare": "Replace zipper slider",
    "Laga slitage": "Repair wear",
    "Laga reva": "Repair tear",
    "Byt ut spänne": "Replace buckle",
    "Ersätt knapp": "Replace button",
    "Laga söm": "Repair seam",
    "Laga brännmärke": "Repair burn mark",
    "Ersätt tryckknapp": "Replace snap button",
    "Byt kardborreband": "Replace velcro",
    "Byt foder": "Replace lining",
    "Byt reflexer": "Replace reflectors",
    "Byt ut resårband": "Replace elastic",
    "Byt jeansknapp": "Replace jeans button",
    "Laga hål": "Repair hole",
    "Laga benslut": "Repair cuffs",
    # Adjustments
    "Korta längden": "Shorten length",
    "Korta benlängder": "Shorten length",  # Same service, different Swedish name
    "Korta ärmar": "Shorten sleeves",
    "Smalna av axelpartiet": "Narrow shoulder area",
    "Smalna av ryggen": "Take in the back",
    "Ta in i sidorna": "Take in sides",
    "Ta i axlar": "Take in shoulders",
    "Ta in midja": "Take in waist",
    "Utöka midja": "Expand waist",
    "Ta in lår": "Take in thigh",
    "Utöka lår": "Expand thigh",
    "Avsmalning av byxben": "Tapering legs",
    # Washing/Care
    "Impregnering": "Waterproofing",
    "Fläckborttagning": "Stain removal",
    "Fläckborttagning och tvätt": "Stain treatment and wash",
    "Fläckbborttagning och tvätt": "Stain treatment and wash",  # typo in QFix
    "Kemtvätt": "Dry cleaning",
    "Vattentvätt": "Waterwash",
    "Rengör och vårda": "Clean and condition",
    # Other
    "Montera ny knapp": "Place new button",
    # Sub-services for length (ignore)
    "längd: 0-1m": None,
    "längd: 1-1,5 m": None,
    "längd: 1,5-2m": None,
    # Category names that leaked into services (ignore)
    "Reparation": None,
    "Anpassa storlek": None,
    "Övriga justeringar": None,
    "Tvätt och skötsel": None,
}

# English service name → list of QFix product IDs (some services have multiple IDs for different price tiers)
EN_TO_IDS = {
    "Replace zipper": [938, 1401, 1395],
    "Replace zipper slider": [942],
    "Repair wear": [928, 1408],
    "Repair tear": [920, 1420],
    "Replace buckle": [947],
    "Replace button": [914],
    "Repair seam": [903, 1443],
    "Repair burn mark": [924, 1416],
    "Replace snap button": [937],
    "Replace velcro": [952],
    "Replace lining": [957],
    "Replace reflectors": [948],
    "Replace elastic": [943],
    "Replace jeans button": [936],
    "Repair hole": [916],
    "Repair cuffs": [962],
    "Shorten length": [1333, 1337],
    "Shorten sleeves": [965, 1355],
    "Narrow shoulder area": [1327],
    "Take in the back": [969, 1328],
    "Take in sides": [968, 1329],
    "Take in shoulders": [971],
    "Take in waist": [958],
    "Expand waist": [960],
    "Take in thigh": [959],
    "Expand thigh": [961, 1373],
    "Tapering legs": [964, 1369],
    "Waterproofing": [1286, 1652, 1252],
    "Stain removal": [1253, 1282],
    "Stain treatment and wash": [1308, 1312],
    "Dry cleaning": [1320, 1322, 1323, 1324, 1325, 1316, 1319],
    "Waterwash": [1349, 1352],
    "Clean and condition": [1294],
    "Place new button": [817],
    "Exchange button": [1432],
    "Attach new inner lining": [972],
    "Replace heel and sole": [1250],
    "Replace sole": [1248],
}

# QFix L3 item variant Swedish name → clothing_type_id mapping
# From the QFix product-categories API
L3_NAME_TO_CT_ID = {
    # Ytterkläder, vuxna (L2 = 54)
    "Fodrad jacka/väst": 61,  # Lined Jacket/Vest
    "Ofodrad jacka/väst": 62, # Unlined Jacket/Vest
    "Kappa": 60,              # Coat
    "Regnjacka": 63,          # Rain jacket
    "Regnbyxa": 64,           # Rain pants
    "Overall": 65,            # Overall
    # Damkläder (L2 = 55)
    "Byxor / Shorts": 84,    # Women's Trousers / Shorts
    "Sweatshirt / Huvtröja": 87, # Women's Sweatshirt / Hoodie
    "Skjorta / Blus": 85,    # Women's Shirt / Blouse
    "Kjol / Klänning": 66,   # Skirt / Dress
    "Stickad tröja": 88,     # Women's Knitted Jumper
    "Kostym / Smoking": 86,  # Women's Suit / Smoking
    "Kavaj": 89,              # Women's Jacket/Blazer
    "Topp / T-shirt": 90,    # Women's Top / T-shirt
    # Herrkläder (L2 = 56)
    # Same names but different IDs — need L2 context
    # Barnkläder (L2 = 57)
    # Same pattern
    # Accessoarer (L2 = 58)
}

# L2 + L3 name → ct_id (to handle same L3 name across different L2s)
L2_L3_TO_CT_ID = {
    # Ytterkläder, vuxna (54)
    ("Ytterkläder, vuxna", "Fodrad jacka/väst"): 61,
    ("Ytterkläder, vuxna", "Ofodrad jacka/väst"): 62,
    ("Ytterkläder, vuxna", "Kappa"): 60,
    ("Ytterkläder, vuxna", "Regnjacka"): 63,
    ("Ytterkläder, vuxna", "Regnbyxa"): 64,
    ("Ytterkläder, vuxna", "Overall"): 65,
    # Damkläder (55)
    ("Damkläder", "Byxor / Shorts"): 84,
    ("Damkläder", "Sweatshirt / Huvtröja"): 87,
    ("Damkläder", "Skjorta / Blus"): 85,
    ("Damkläder", "Kjol / Klänning"): 66,
    ("Damkläder", "Stickad tröja"): 88,
    ("Damkläder", "Kostym / Smoking"): 86,
    ("Damkläder", "Kavaj"): 89,
    ("Damkläder", "Topp / T-shirt"): 90,
    ("Damkläder", "Kostym"): 86,  # Same as Kostym / Smoking for women
    # Herrkläder (56)
    ("Herrkläder", "Byxor / Shorts"): 91,
    ("Herrkläder", "Kostym"): 92,
    ("Herrkläder", "Kavaj"): 93,
    ("Herrkläder", "Sweatshirt / Huvtröja"): 94,
    ("Herrkläder", "Stickad tröja"): 95,
    ("Herrkläder", "Skjortor/t-shirts"): 96,
    ("Herrkläder", "Kostym / Smoking"): 92,  # Same as Kostym
    # Barnkläder (57)
    ("Barnkläder", "Byxor / Shorts"): 104,
    ("Barnkläder", "Skjorta / t-shirt / Body"): 106,
    ("Barnkläder", "Stickad tröja"): 105,
    ("Barnkläder", "Sweatshirt / Huvtröja"): 107,
    ("Barnkläder", "Overall"): 108,
    ("Barnkläder", "Kostym"): 109,
    ("Barnkläder", "Kavaj"): 110,
    ("Barnkläder", "Övrigt"): 175,  # Other
    # Accessoarer (58)
    ("Accessoarer", "Halsduk / Sjal"): 99,
    ("Accessoarer", "Keps"): 100,
    ("Accessoarer", "Hatt"): 101,
    ("Accessoarer", "Handskar"): 102,
    ("Accessoarer", "Bälte"): 103,
    ("Accessoarer", "Övriga"): 175,
    ("Accessoarer", "Underkläder"): 111,
    ("Accessoarer", "Övrigt"): 175,  # May need to verify
}

# L4 material Swedish name → material_id
L4_NAME_TO_MAT_ID = {
    "Standard textil": 69,
    "Standard-textil": 69,  # alternate spelling
    "Dun": 176,
    "Läder/Mocka": 71,
    "Päls": 72,
    "Annat/osäker": 73,
    "Linne/ull": 70,
    "Kashmir": 166,
    "Silk": 213,
    "Highvis": 83,
    "Spets": 214,  # May need to verify
}

# L5 service category Swedish → English key
L5_TO_KEY = {
    "Reparation": "repair",
    "Anpassa storlek": "adjustment",
    "Övriga justeringar": "other",
    "Tvätt och skötsel": "care",
}


def process_crawl():
    with open("/Users/oscar/kappahl/qfix_crawl_raw.json") as f:
        crawl_data = json.load(f)

    result = {}  # ct_id → mat_id → service_key → [{"id": ..., "name": ...}]
    unmapped_l3 = set()
    unmapped_l4 = set()
    unmapped_svc = set()

    for path, data in crawl_data.items():
        l2 = data["l2"]
        l3 = data["l3"]
        l4 = data["l4"]
        l5 = data["l5_service_category"]

        # Map to IDs
        ct_id = L2_L3_TO_CT_ID.get((l2, l3))
        if ct_id is None:
            unmapped_l3.add((l2, l3))
            continue

        mat_id = L4_NAME_TO_MAT_ID.get(l4)
        if mat_id is None:
            unmapped_l4.add(l4)
            continue

        svc_key = L5_TO_KEY.get(l5)
        if svc_key is None:
            continue

        ct_str = str(ct_id)
        mat_str = str(mat_id)
        if ct_str not in result:
            result[ct_str] = {}
        if mat_str not in result[ct_str]:
            result[ct_str][mat_str] = {}

        # Map services
        services = []
        for svc in data["services"]:
            sv_name = svc["name"]
            en_name = SV_TO_EN.get(sv_name)
            if en_name is None:
                if sv_name not in SV_TO_EN:
                    unmapped_svc.add(sv_name)
                continue  # Skip None (ignored) or unmapped

            ids = EN_TO_IDS.get(en_name, [])
            if not ids:
                unmapped_svc.add(f"{sv_name} -> {en_name} (no IDs)")
                continue

            for pid in ids:
                services.append({"id": pid, "name": en_name})

        result[ct_str][mat_str][svc_key] = services

    # Report unmapped
    if unmapped_l3:
        print(f"Unmapped L2+L3 combinations: {unmapped_l3}")
    if unmapped_l4:
        print(f"Unmapped L4 materials: {unmapped_l4}")
    if unmapped_svc:
        print(f"Unmapped services: {unmapped_svc}")

    # Save result
    output_path = "/Users/oscar/kappahl/qfix_services_by_type.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Summary
    total_combos = sum(
        len(mats)
        for mats in result.values()
    )
    print(f"\nSaved {len(result)} clothing types, {total_combos} ct+mat combos to {output_path}")

    # Show a comparison for T-shirt vs Trousers
    print("\n=== Example: Women's Trousers (84) vs Women's T-shirt (90) ===")
    for ct_id, label in [("84", "Women's Trousers"), ("90", "Women's T-shirt")]:
        print(f"\n{label} (ct_id={ct_id}):")
        ct = result.get(ct_id, {})
        for mat_id, mats in ct.items():
            print(f"  Material {mat_id}:")
            for svc_key, services in mats.items():
                names = list(set(s["name"] for s in services))
                print(f"    {svc_key}: {len(names)} - {names}")


if __name__ == "__main__":
    process_crawl()
