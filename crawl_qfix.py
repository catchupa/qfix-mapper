#!/usr/bin/env python3
"""
Crawl the QFix booking wizard to capture which services are available
for each clothing type + material + service category combination.

For each path through the wizard, we reload the page and click through
all steps since back navigation is unreliable.

Output: qfix_services_by_type.json
"""

import json
import time
import re
import sys
from playwright.sync_api import sync_playwright


BASE_URL = "https://kappahl.dev.qfixr.me/sv/"
WAIT = 1.0  # seconds between clicks


def wait_for_loader(page, timeout=10000):
    """Wait for the loading spinner to disappear."""
    try:
        loader = page.query_selector("#loader")
        if loader and loader.is_visible():
            page.wait_for_selector("#loader", state="hidden", timeout=timeout)
    except:
        pass
    # Also wait for any spinner
    try:
        page.wait_for_selector(".spinner-border", state="hidden", timeout=3000)
    except:
        pass


def get_visible_step(page):
    """Return the currently visible step number and element."""
    for i in range(1, 10):
        el = page.query_selector(f"#step{i}")
        if el:
            cls = el.get_attribute("class") or ""
            if "hidden" not in cls:
                return i, el
    return None, None


def get_step_buttons(step_el):
    """Get all meaningful buttons in a step."""
    buttons = step_el.query_selector_all("button.select-item")
    result = []
    for btn in buttons:
        if not btn.is_visible():
            continue
        # Get just the button text (not price spans)
        full_text = btn.inner_text().strip()
        # Extract name (before price)
        name = full_text.split("\n")[0].strip()
        if not name:
            continue
        # Extract price if present
        price_span = btn.query_selector(".variant-price")
        price = price_span.inner_text().strip() if price_span else ""
        result.append({"name": name, "price": price, "element": btn})
    return result


def navigate_and_click(page, path_indices):
    """Navigate from start to a specific path through the wizard.
    path_indices: list of button indices to click at each step.
    Returns the step element after the last click, or None if failed.
    """
    # Start fresh with retry
    for attempt in range(3):
        try:
            page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            break
        except Exception as e:
            if attempt == 2:
                print(f"    Failed to load page after 3 attempts: {e}")
                return None
            time.sleep(5)
    time.sleep(WAIT)

    # Click "Kläder"
    klader = page.query_selector('li[data-cat-id="49"]')
    if not klader:
        return None
    klader.click()
    time.sleep(WAIT)
    wait_for_loader(page)

    # Click through each step
    for idx in path_indices:
        step_num, step_el = get_visible_step(page)
        if not step_el:
            return None
        buttons = get_step_buttons(step_el)
        if idx >= len(buttons):
            return None
        buttons[idx]["element"].click(timeout=15000)
        time.sleep(WAIT)
        wait_for_loader(page)

    step_num, step_el = get_visible_step(page)
    return step_el


def crawl_qfix():
    # Load existing results to resume
    existing_path = "/Users/oscar/kappahl/qfix_crawl_raw.json"
    try:
        with open(existing_path) as f:
            all_results = json.load(f)
        print(f"Loaded {len(all_results)} existing results, resuming...")
    except:
        all_results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Step 1: Get L2 items
        page.goto(BASE_URL, wait_until="networkidle")
        time.sleep(WAIT)
        page.query_selector('li[data-cat-id="49"]').click()
        time.sleep(WAIT)

        _, step2 = get_visible_step(page)
        l2_items = get_step_buttons(step2)
        l2_names = [b["name"] for b in l2_items]
        print(f"L2 items ({len(l2_names)}): {l2_names}")

        for l2_idx, l2_name in enumerate(l2_names):
            print(f"\n{'='*60}")
            print(f"L2: {l2_name} ({l2_idx+1}/{len(l2_names)})")
            print(f"{'='*60}")

            # Navigate to L3 for this L2
            step3 = navigate_and_click(page, [l2_idx])
            if not step3:
                print(f"  Failed to reach L3 for {l2_name}")
                continue

            l3_items = get_step_buttons(step3)
            l3_names = [b["name"] for b in l3_items]
            print(f"  L3 items ({len(l3_names)}): {l3_names}")

            for l3_idx, l3_name in enumerate(l3_names):
                print(f"\n  L3: {l3_name} ({l3_idx+1}/{len(l3_names)})")

                # Navigate to L4
                step4 = navigate_and_click(page, [l2_idx, l3_idx])
                if not step4:
                    print(f"    Failed to reach L4")
                    continue

                l4_items = get_step_buttons(step4)
                l4_names = [b["name"] for b in l4_items]
                print(f"    L4 materials ({len(l4_names)}): {l4_names}")

                for l4_idx, l4_name in enumerate(l4_names):
                    print(f"    L4: {l4_name} ({l4_idx+1}/{len(l4_names)})")

                    # Navigate to L5
                    step5 = navigate_and_click(page, [l2_idx, l3_idx, l4_idx])
                    if not step5:
                        print(f"      Failed to reach L5")
                        continue

                    l5_items = get_step_buttons(step5)
                    l5_names = [b["name"] for b in l5_items]
                    print(f"      L5 categories ({len(l5_names)}): {l5_names}")

                    for l5_idx, l5_name in enumerate(l5_names):
                        key = f"{l2_name} > {l3_name} > {l4_name} > {l5_name}"
                        if key in all_results:
                            print(f"        {l5_name}: SKIP (already crawled)")
                            continue
                        try:
                            # Navigate to L6 (services)
                            step6 = navigate_and_click(page, [l2_idx, l3_idx, l4_idx, l5_idx])
                            if not step6:
                                print(f"        Failed to reach services for {l5_name}")
                                continue

                            services = get_step_buttons(step6)
                            svc_list = [{"name": s["name"], "price": s["price"]} for s in services]

                            all_results[key] = {
                                "l2": l2_name,
                                "l3": l3_name,
                                "l4": l4_name,
                                "l5_service_category": l5_name,
                                "services": svc_list,
                                "service_count": len(svc_list),
                            }

                            svc_names = [s["name"] for s in svc_list]
                            print(f"        {l5_name}: {len(svc_list)} services - {svc_names}")

                            # Save intermediate results
                            with open("/Users/oscar/kappahl/qfix_crawl_raw.json", "w") as f:
                                json.dump(all_results, f, indent=2, ensure_ascii=False)
                        except Exception as e:
                            print(f"        ERROR for {l5_name}: {e}")

        browser.close()

    # Save results
    output_path = "/Users/oscar/kappahl/qfix_crawl_raw.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(all_results)} combinations to {output_path}")

    # Summary: compare service counts across L3 items
    print(f"\n{'='*60}")
    print("SUMMARY: Service counts per L3 item variant")
    print(f"{'='*60}")
    by_l3 = {}
    for key, data in all_results.items():
        l3 = data["l3"]
        l5 = data["l5_service_category"]
        count = data["service_count"]
        if l3 not in by_l3:
            by_l3[l3] = {}
        by_l3[l3][l5] = count
    for l3, cats in sorted(by_l3.items()):
        print(f"  {l3}: {dict(cats)}")

    return all_results


if __name__ == "__main__":
    crawl_qfix()
