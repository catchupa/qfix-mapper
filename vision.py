"""Vision-based product identification using Claude Vision API."""
import base64
import io
import json
import logging
import os

import anthropic
from PIL import Image

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

VISION_PROMPT = """Look at this image of a garment or clothing item. Identify the following properties:

1. clothing_type: Choose exactly one from this list:
   Jacket, Coat, Unlined Jacket / Vest, Lined Jacket / Vest, Top / T-shirt, T-shirt, Shirt / Blouse, Knitted Jumper, Sweater, Sweatshirt / Hoodie, Midlayer, Trousers, Trousers / Shorts, Skirt / Dress, Suit, Swimsuit, Bikini, Underwear, Overall, Hat, Cap, Gloves, Scarf / Shawl, Belt, Handbags, Other

2. material: Choose exactly one from this list based on what you can see:
   Standard textile, Linen/Wool, Cashmere, Silk, Leather/Suede, Down, Fur, Other/Unsure

   Guidelines:
   - "Standard textile" = cotton, polyester, denim, nylon, elastane, viscose, or any common synthetic
   - "Linen/Wool" = visible linen or wool texture
   - "Leather/Suede" = leather or suede appearance
   - "Down" = puffy/quilted down jackets
   - If unsure, use "Standard textile" for most clothing or "Other/Unsure" if truly unclear

3. color: The main color of the item (e.g. "Black", "Blue", "White", "Red")

4. category: Choose one from: Women's Clothing, Men's Clothing, Children's Clothing
   If unclear, default to Women's Clothing.

Respond with ONLY a JSON object, no other text:
{"clothing_type": "...", "material": "...", "color": "...", "category": "..."}"""


def identify_product(image_bytes, media_type="image/jpeg"):
    """Send an image to Claude Vision API and get product classification.

    Args:
        image_bytes: Raw image bytes
        media_type: MIME type (image/jpeg, image/png, image/webp, image/gif)

    Returns:
        dict with clothing_type, material, color, category
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Resize if image exceeds 5 MB API limit
    MAX_BYTES = 5 * 1024 * 1024
    if len(image_bytes) > MAX_BYTES:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((2048, 2048), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        image_bytes = buf.getvalue()
        media_type = "image/jpeg"
        logger.info("Resized image to %d bytes", len(image_bytes))

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": VISION_PROMPT,
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text.strip()

    # Parse JSON from response (handle markdown code blocks)
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    try:
        classification = json.loads(response_text)
    except json.JSONDecodeError:
        logger.error("Failed to parse vision response: %s", response_text)
        classification = {
            "clothing_type": "Other",
            "material": "Other/Unsure",
            "color": "Unknown",
            "category": "Women's Clothing",
        }

    return classification


def classify_and_map(image_bytes, media_type="image/jpeg"):
    """Identify a product from an image and map to QFix categories.

    Returns dict with 'classification' and 'qfix' keys.
    """
    from mapping import QFIX_CLOTHING_TYPE_IDS, QFIX_SUBCATEGORY_IDS, VALID_MATERIAL_IDS, _resolve_material_id

    classification = identify_product(image_bytes, media_type)

    clothing_name = classification.get("clothing_type", "Other")
    material_name = classification.get("material", "Other/Unsure")
    subcategory_name = classification.get("category", "Women's Clothing")

    clothing_type_id = QFIX_CLOTHING_TYPE_IDS.get(clothing_name)
    material_id = _resolve_material_id(clothing_type_id, material_name)
    subcategory_id = QFIX_SUBCATEGORY_IDS.get(subcategory_name)

    qfix_url = None
    if clothing_type_id and material_id:
        qfix_url = f"https://kappahl.dev.qfixr.me/sv/?category_id={clothing_type_id}&material_id={material_id}"
    elif clothing_type_id:
        qfix_url = f"https://kappahl.dev.qfixr.me/sv/?category_id={clothing_type_id}"

    return {
        "classification": classification,
        "qfix": {
            "qfix_clothing_type": clothing_name,
            "qfix_clothing_type_id": clothing_type_id,
            "qfix_material": material_name,
            "qfix_material_id": material_id,
            "qfix_subcategory": subcategory_name,
            "qfix_subcategory_id": subcategory_id,
            "qfix_url": qfix_url,
        },
    }
