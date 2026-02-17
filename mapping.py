"""
Maps scraped products to QFix repair service categories.

Scraper hierarchy: category (dam/herr) > clothing_type > material
QFix hierarchy:    L1 (Clothing/Shoes/Bags) > L2 (Outerwear/Women's/Men's) >
                   L3 (clothing type) > L4 (material) > L5 (service type)

The complete QFix catalog is fetched from:
  https://dev.qfixr.me/wp-json/qfix/v1/product-categories?parent=23

Legacy dicts (suffix _LEGACY) preserve the original hand-curated mapping
for comparison and fallback.
"""
import re

# ══════════════════════════════════════════════════════════════════════════
# LEGACY QFix IDs (original hand-curated mapping)
# ══════════════════════════════════════════════════════════════════════════

QFIX_CLOTHING_TYPE_IDS_LEGACY = {
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

VALID_MATERIAL_IDS_LEGACY = {
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
}

QFIX_SUBCATEGORY_IDS_LEGACY = {
    "Outerwear": 54,
    "Women's Clothing": 55,
    "Men's Clothing": 56,
    "Children's Clothing": 58,
    "Accessories": 57,
    "Swimwear / Wet suits": 167,
}

# ══════════════════════════════════════════════════════════════════════════
# COMPLETE QFix IDs (from API, all 88 clothing types)
# ══════════════════════════════════════════════════════════════════════════

# When a name appears in multiple subcategories (e.g. "Boots" in Men's/Women's/
# Children's/Workwear Shoes), one representative ID is kept here. All IDs are
# present in VALID_MATERIAL_IDS for correct material resolution.
QFIX_CLOTHING_TYPE_IDS = {
    "Ancle boots": 205,
    "Backpack": 121,
    "Belt": 102,
    "Bikini": 201,
    "Boots": 110,              # also: 113 (Women's), 138 (Workwear), 182 (MC)
    "Briefcase": 122,
    "Cap": 99,
    "Coat": 60,
    "Dress Shoes": 111,        # also: 116 (Women's)
    "Gloves": 100,
    "Handbags": 123,
    "Hat": 98,
    "High heels": 114,
    "Highvis jacket": 81,
    "Jacket": 173,             # also: 85 (Women's), 93 (Men's), 103 (Children's)
    "Knee-high boots": 206,
    "Knitted Jumper": 87,      # also: 95 (Men's), 193 (Children's)
    "Large (more than 6sqm)": 130,
    "Larger Bag / Duffel": 124,
    "Lined Jacket / Vest": 61,
    "Medium (3 to 6sqm)": 129,
    "Midlayer": 161,
    "Other": 105,
    "Other shoes": 146,
    "Others": 200,             # also: 202 (Workwear), 203 (MC)
    "Overall": 198,            # also: 199 (Children's), 175 (MC)
    "Overalls": 160,
    "Rain Jacket": 142,
    "Rain Trousers": 185,
    "Rain boots": 148,         # also: 149 (Women's), 150 (Workwear), 147 (Children's)
    "Sandals": 165,            # also: 164 (Women's), 141 (Workwear)
    "Scarf / Shawl": 101,
    "Shirt / Blouse": 89,
    "Shirt / t-shirt / Body": 194,
    "Shirts/t-shirts": 96,
    "Shoes": 140,              # also: 183 (MC)
    "Ski / Shell Trousers": 80,
    "Ski / Shell jacket": 78,
    "Skirt / Dress": 66,
    "Small (less than 3sqm)": 128,
    "Sneakers": 112,           # also: 115 (Women's)
    "Suit": 86,
    "Suit / Smoking": 92,      # also: 195 (Children's)
    "Sweater": 162,
    "Sweatshirt / Hoodie": 88, # also: 94 (Men's), 196 (Children's)
    "Swimming trunks": 169,
    "Swimsuit": 168,
    "T-shirt": 163,
    "Top / T-shirt": 90,
    "Trousers": 174,           # also: 82 (Workwear)
    "Trousers / Shorts": 84,   # also: 91 (Men's), 104 (Children's)
    "Underwear": 171,
    "Unlined Jacket / Vest": 62,
    "Weekend Bag": 125,
    "Wet suit": 170,
    "Winter boots": 145,
}

# Valid material IDs per clothing type ID (from QFix API tree).
# Clothing and shoe categories use DIFFERENT IDs for the same material name.
# e.g. "Standard textile" = 69 for clothing, 189 for shoes.
VALID_MATERIAL_IDS = {
    60:  {69: "Standard textile", 71: "Leather/Suede", 72: "Fur", 73: "Other/Unsure"},                                           # Coat (Outerwear)
    61:  {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 72: "Fur", 83: "Highvis", 73: "Other/Unsure"},                # Lined Jacket / Vest (Outerwear)
    62:  {69: "Standard textile", 71: "Leather/Suede", 166: "Linen/Wool", 143: "Galloon", 83: "Highvis", 73: "Other/Unsure"},     # Unlined Jacket / Vest (Outerwear)
    66:  {69: "Standard textile", 71: "Leather/Suede", 166: "Linen/Wool", 213: "Silk", 73: "Other/Unsure"},                       # Skirt / Dress (Women's)
    78:  {69: "Standard textile", 176: "Down", 73: "Other/Unsure"},                                                               # Ski / Shell jacket (Outerwear)
    80:  {69: "Standard textile", 176: "Down", 73: "Other/Unsure"},                                                               # Ski / Shell Trousers (Outerwear)
    81:  {69: "Standard textile", 176: "Down", 143: "Galloon", 83: "Highvis", 73: "Other/Unsure"},                                # Highvis jacket (Workwear)
    82:  {69: "Standard textile", 83: "Highvis", 144: "Flame resistant", 73: "Other/Unsure"},                                     # Trousers (Workwear)
    84:  {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Trousers / Shorts (Women's)
    85:  {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 73: "Other/Unsure"},                                        # Jacket (Women's)
    86:  {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 73: "Other/Unsure"},                                        # Suit (Women's)
    87:  {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 73: "Other/Unsure"},                                        # Knitted Jumper (Women's)
    88:  {69: "Standard textile", 73: "Other/Unsure"},                                                                            # Sweatshirt / Hoodie (Women's)
    89:  {69: "Standard textile", 166: "Linen/Wool", 213: "Silk", 73: "Other/Unsure"},                                            # Shirt / Blouse (Women's)
    90:  {69: "Standard textile", 73: "Other/Unsure"},                                                                            # Top / T-shirt (Women's)
    91:  {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Trousers / Shorts (Men's)
    92:  {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Suit / Smoking (Men's)
    93:  {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Jacket (Men's)
    94:  {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Sweatshirt / Hoodie (Men's)
    95:  {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 73: "Other/Unsure"},                                        # Knitted Jumper (Men's)
    96:  {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 213: "Silk", 73: "Other/Unsure"},                           # Shirts/t-shirts (Men's)
    98:  {69: "Standard textile", 72: "Fur", 73: "Other/Unsure"},                                                                 # Hat (Accessories)
    99:  {69: "Standard textile", 71: "Leather/Suede", 83: "Highvis", 73: "Other/Unsure"},                                        # Cap (Accessories)
    100: {69: "Standard textile", 71: "Leather/Suede", 213: "Silk", 73: "Other/Unsure"},                                          # Gloves (Accessories)
    101: {69: "Standard textile", 166: "Linen/Wool", 159: "Cashmere", 72: "Fur", 213: "Silk", 73: "Other/Unsure"},                # Scarf / Shawl (Accessories)
    102: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},                                                       # Belt (Accessories)
    103: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Jacket (Children's)
    104: {69: "Standard textile", 73: "Other/Unsure"},                                                                            # Trousers / Shorts (Children's)
    105: {166: "Linen/Wool", 213: "Silk", 214: "Lace", 215: "Tulle", 73: "Other/Unsure"},                                        # Other (Children's)
    110: {189: "Standard textile", 187: "Leather", 191: "Other/Unsure"},                                                          # Boots (Men's Shoes)
    111: {187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                                                     # Dress Shoes (Men's Shoes)
    112: {189: "Standard textile", 188: "Suede", 191: "Other/Unsure"},                                                            # Sneakers (Men's Shoes)
    113: {189: "Standard textile", 187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                            # Boots (Women's Shoes)
    114: {187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                                                     # High heels (Women's Shoes)
    115: {189: "Standard textile", 188: "Suede", 191: "Other/Unsure"},                                                            # Sneakers (Women's Shoes)
    116: {187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                                                     # Dress Shoes (Women's Shoes)
    121: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},                                                          # Backpack
    122: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},                                                          # Briefcase
    123: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},                                                          # Handbags
    124: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},                                                          # Larger Bag / Duffel
    125: {69: "Standard textile", 71: "Leather/Suede", 73: "Other/Unsure"},                                                          # Weekend Bag
    138: {189: "Standard textile", 187: "Leather", 191: "Other/Unsure"},                                                          # Boots (Workwear Shoes)
    140: {189: "Standard textile", 187: "Leather", 191: "Other/Unsure"},                                                          # Shoes (Workwear Shoes)
    141: {189: "Standard textile", 187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                            # Sandals (Workwear Shoes)
    142: {69: "Standard textile", 83: "Highvis", 73: "Other/Unsure"},                                                             # Rain Jacket (Outerwear)
    145: {189: "Standard textile", 187: "Leather", 191: "Other/Unsure"},                                                          # Winter boots (Children's Shoes)
    146: {189: "Standard textile", 187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                            # Other shoes (Children's Shoes)
    147: {190: "Galloon", 191: "Other/Unsure"},                                                                                   # Rain boots (Children's Shoes)
    148: {190: "Galloon", 191: "Other/Unsure"},                                                                                   # Rain boots (Men's Shoes)
    149: {190: "Galloon", 191: "Other/Unsure"},                                                                                   # Rain boots (Women's Shoes)
    150: {190: "Galloon", 191: "Other/Unsure"},                                                                                   # Rain boots (Workwear Shoes)
    160: {69: "Standard textile", 176: "Down", 83: "Highvis", 144: "Flame resistant", 73: "Other/Unsure"},                        # Overalls (Workwear)
    161: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Midlayer (Workwear)
    162: {69: "Standard textile", 73: "Other/Unsure"},                                                                            # Sweater (Workwear)
    163: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # T-shirt (Workwear)
    164: {189: "Standard textile", 187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                            # Sandals (Women's Shoes)
    165: {189: "Standard textile", 187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                            # Sandals (Men's Shoes)
    168: {69: "Standard textile", 213: "Silk", 73: "Other/Unsure"},                                                               # Swimsuit
    169: {69: "Standard textile", 213: "Silk", 73: "Other/Unsure"},                                                               # Swimming trunks
    170: {69: "Standard textile", 73: "Other/Unsure"},                                                                            # Wet suit
    171: {69: "Standard textile", 166: "Linen/Wool", 213: "Silk", 73: "Other/Unsure"},                                            # Underwear (Accessories)
    173: {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 73: "Other/Unsure"},                                          # Jacket (MC)
    174: {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 73: "Other/Unsure"},                                          # Trousers (MC)
    175: {69: "Standard textile", 176: "Down", 71: "Leather/Suede", 83: "Highvis", 73: "Other/Unsure"},                           # Overall (MC)
    182: {189: "Standard textile", 187: "Leather", 191: "Other/Unsure"},                                                          # Boots (MC Shoes)
    183: {189: "Standard textile", 187: "Leather", 191: "Other/Unsure"},                                                          # Shoes (MC Shoes)
    185: {69: "Standard textile", 143: "Galloon", 83: "Highvis", 73: "Other/Unsure"},                                             # Rain Trousers (Outerwear)
    193: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Knitted Jumper (Children's)
    194: {69: "Standard textile", 73: "Other/Unsure"},                                                                            # Shirt / t-shirt / Body (Children's)
    195: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Suit / Smoking (Children's)
    196: {69: "Standard textile", 73: "Other/Unsure"},                                                                            # Sweatshirt / Hoodie (Children's)
    198: {69: "Standard textile", 176: "Down", 83: "Highvis", 144: "Flame resistant", 73: "Other/Unsure"},                        # Overall (Outerwear)
    199: {69: "Standard textile", 166: "Linen/Wool", 73: "Other/Unsure"},                                                         # Overall (Children's)
    200: {69: "Standard textile", 71: "Leather/Suede", 166: "Linen/Wool", 72: "Fur", 144: "Flame resistant", 73: "Other/Unsure"}, # Others (Accessories)
    201: {69: "Standard textile", 213: "Silk", 73: "Other/Unsure"},                                                               # Bikini
    202: {71: "Leather/Suede", 166: "Linen/Wool", 83: "Highvis", 144: "Flame resistant", 73: "Other/Unsure"},                     # Others (Workwear)
    203: {71: "Leather/Suede", 83: "Highvis", 144: "Flame resistant", 73: "Other/Unsure"},                                        # Others (MC)
    205: {189: "Standard textile", 187: "Leather", 188: "Suede", 191: "Other/Unsure"},                                            # Ancle boots (Riding)
    206: {189: "Standard textile", 187: "Leather", 188: "Suede"},                                                                 # Knee-high boots (Riding)
}

QFIX_SUBCATEGORY_IDS = {
    "Outerwear": 54,
    "Women's Clothing": 55,
    "Men's Clothing": 56,
    "Accessories": 57,
    "Children's Clothing": 58,
    "Workwear": 59,
    "Backpack": 75,
    "Men's Shoes": 106,
    "Women's Shoes": 107,
    "Children's Shoes": 108,
    "Workwear Shoes": 109,
    "Briefcase": 117,
    "Handbags": 118,
    "Larger bag / Duffel": 119,
    "Weekend Bag": 120,
    "Handmade carpet": 126,
    "Other Carpet": 127,
    "Swimwear / Wet suits": 167,
    "Protective / MC wear": 172,
    "Carpet with rubber bottom": 177,
    "Protective / MC shoes": 181,
    "Riding boots": 204,
}

# ── Scraper → QFix name mappings ─────────────────────────────────────────

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
    # Eton clothing types
    "businesskjortor": "Shirt / Blouse",
    "casualskjortor": "Shirt / Blouse",
    "frack- och smokingskjortor": "Shirt / Blouse",
    "jackor & overshirts": "Jacket",
    "knitwear": "Knitted Jumper",
    "polo shirts": "Top / T-shirt",
    "t-shirt": "T-shirt",
    "vests": "Unlined Jacket / Vest",
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
    # English names (from other brand scrapers)
    "cotton": "Standard textile",
    "organic cotton": "Standard textile",
    "recycled cotton": "Standard textile",
    "polyamide": "Standard textile",
    "elastane": "Standard textile",
    "viscose": "Standard textile",
    "acrylic": "Standard textile",
    "hemp": "Standard textile",
    # Linen / Wool
    "lin": "Linen/Wool",
    "linne": "Linen/Wool",
    "ull": "Linen/Wool",
    "certifierad ull": "Linen/Wool",
    "återvunnen ull": "Linen/Wool",
    "linen": "Linen/Wool",
    "wool": "Linen/Wool",
    # Premium materials
    "kashmir": "Cashmere",
    "kasjmir": "Cashmere",
    "cashmere": "Cashmere",
    "siden": "Silk",
    "silke": "Silk",
    "silk": "Silk",
    # Leather
    "läder": "Leather/Suede",
    "skinn": "Leather/Suede",
    "vegetabiliskt garvat": "Leather/Suede",
    "leather": "Leather/Suede",
    "suede": "Leather/Suede",
    # Down
    "dun": "Down",
    "down": "Down",
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
    # English categories (from other brand scrapers)
    "women": "Women's Clothing",
    "men": "Men's Clothing",
    "men's jeans": "Men's Clothing",
    "women's jeans": "Women's Clothing",
    "kids": "Children's Clothing",
    "jeans": "Men's Clothing",
    # Eton
    "businesskjortor": "Men's Clothing",
    "casualskjortor": "Men's Clothing",
    "accessoarer": "Accessories",
}


# ── Mapping functions ────────────────────────────────────────────────────

SKIP_SEGMENTS = {"dam", "herr", "barn", "baby"}


def map_clothing_type(kappahl_clothing_type):
    """Map clothing_type string to QFix L3 clothing type name."""
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
    """Map material composition to QFix L4 material category name."""
    if not kappahl_material:
        return "Other/Unsure"

    # Support both "75% Bomull, 21% Polyester" and "98% Cotton 2% Elastane"
    matches = re.findall(r"(\d{1,3})%\s*(.+?)(?:,\s*|(?=\s+\d{1,3}%)|$)", kappahl_material)
    # Also support reversed format: "Cotton 100%"
    if not matches:
        matches = re.findall(r"(.+?)\s+(\d{1,3})%", kappahl_material)
        matches = [(pct, name) for name, pct in matches]
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
    """Map category (dam/herr) to QFix L2 name."""
    if not kappahl_category:
        return "Women's Clothing"
    return CATEGORY_MAP.get(kappahl_category.lower(), "Women's Clothing")


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
    """Map a product dict to QFix IDs using the complete catalog.

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


def map_product_legacy(product):
    """Map a product dict to QFix IDs using the original hand-curated mapping.

    Same interface as map_product() but uses _LEGACY dicts.
    """
    clothing_name = map_clothing_type(product.get("clothing_type"))
    material_name = map_material(product.get("material_composition"))
    subcategory_name = map_category(product.get("category"))

    clothing_type_id = QFIX_CLOTHING_TYPE_IDS_LEGACY.get(clothing_name) if clothing_name else None

    # Use legacy material IDs
    material_id = None
    if clothing_type_id and material_name:
        valid = VALID_MATERIAL_IDS_LEGACY.get(clothing_type_id, {})
        for mat_id, mat_name in valid.items():
            if mat_name == material_name:
                material_id = mat_id
                break
        if material_id is None:
            for mat_id, mat_name in valid.items():
                if mat_name == "Other/Unsure":
                    material_id = mat_id
                    break

    qfix_url = None
    if clothing_type_id and material_id:
        qfix_url = f"https://kappahl.dev.qfixr.me/sv/?category_id={clothing_type_id}&material_id={material_id}"

    return {
        "qfix_clothing_type": clothing_name,
        "qfix_clothing_type_id": clothing_type_id,
        "qfix_material": material_name,
        "qfix_material_id": material_id,
        "qfix_subcategory": subcategory_name,
        "qfix_subcategory_id": QFIX_SUBCATEGORY_IDS_LEGACY.get(subcategory_name),
        "qfix_url": qfix_url,
    }
