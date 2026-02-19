# QFix Repair Widget — Integration Guide

Add a "Repair this item" button to your product pages. When a customer clicks it, they are taken directly to the QFix repair booking page with the correct service category pre-selected for that product.

## Live demo

See the widget in action on a sample product page:
https://kappahl-qfix.fly.dev/demo/

---

## Integration (2 steps)

### Step 1: Add the placeholder element

Place this `<div>` wherever you want the repair button to appear on your product page — typically below the "Add to cart" button:

```html
<div id="qfix-repair"
     data-product-id="YOUR_PRODUCT_ID"
     data-brand="YOUR_BRAND_SLUG"
     data-api-key="YOUR_API_KEY">
</div>
```

Replace:
- `YOUR_PRODUCT_ID` with the product's article number (e.g. `530956`)
- `YOUR_BRAND_SLUG` with your brand identifier (see table below)
- `YOUR_API_KEY` with the API key provided by the QFix team

| Brand        | Slug          |
|--------------|---------------|
| KappAhl      | `kappahl`     |
| Gina Tricot  | `ginatricot`  |
| Eton         | `eton`        |
| Nudie Jeans  | `nudie`       |
| Lindex       | `lindex`      |

### Step 2: Load the widget script

Add this script tag at the bottom of your page, before `</body>`:

```html
<script src="https://kappahl-qfix.fly.dev/widget.js"></script>
```

### Complete example

```html
<!-- Eager: fetches on page load -->
<div id="qfix-repair" data-product-id="530956" data-brand="kappahl" data-api-key="your-key-here"></div>

<!-- Or lazy: fetches only when clicked -->
<div id="qfix-repair" data-product-id="530956" data-brand="kappahl" data-api-key="your-key-here" data-lazy></div>

<!-- Load the widget (before </body>) -->
<script src="https://kappahl-qfix.fly.dev/widget.js"></script>
```

That's it. The widget handles everything else automatically.

---

## Loading modes

The widget supports two loading modes: **eager** (default) and **lazy**.

### Eager loading (default)

The widget makes an API request as soon as the page loads. If a repair service is available, the button appears automatically. If not, nothing is shown.

1. The script runs when the page loads
2. It looks up your product against the QFix product database
3. If a repair service is available, a styled "Reparera" button appears
4. If the product can't be matched, nothing is shown — no empty space, no errors
5. Clicking the button opens the QFix repair booking page in a new tab

```html
<div id="qfix-repair" data-product-id="530956" data-brand="kappahl" data-api-key="your-key-here"></div>
```

### Lazy loading

Add the `data-lazy` attribute to defer the API request until the user clicks the button. The widget renders a placeholder "Reparera" button immediately — no network request is made on page load. When the user clicks, the widget fetches the repair URL and redirects.

This is useful when:
- You have many product pages and want to reduce API load
- Page load performance is a priority
- The repair button is below the fold or secondary to the main content

```html
<div id="qfix-repair" data-product-id="530956" data-brand="kappahl" data-api-key="your-key-here" data-lazy></div>
```

**Lazy loading flow:**
1. Page loads — a styled "Reparera" button appears immediately (no API call)
2. User clicks the button
3. The widget fetches the product data from the API (loading animation shown)
4. If a repair service is available, the button is replaced with a link to the repair page
5. If the product can't be matched, the button is removed

---

## Options

### API key

Each brand receives a unique API key for authentication. Set it via the `data-api-key` attribute on the widget div. Requests without a valid key will receive a `401` error.

```html
<div id="qfix-repair" data-product-id="530956" data-brand="kappahl" data-api-key="your-key-here"></div>
```

### Theme

The widget comes in two variants. Set the `data-theme` attribute to match your page background:

| Value   | Button style                          | Use when                    |
|---------|---------------------------------------|-----------------------------|
| `light` | Dark button (black background, white text) | Light/white page background (default) |
| `dark`  | Light button (white background, dark text) | Dark page background        |

```html
<div id="qfix-repair" data-product-id="530956" data-brand="kappahl" data-theme="dark"></div>
```

### Multiple buttons on the same page

If you need more than one repair button on a page (e.g. a product bundle), use `data-qfix` instead of `id`:

```html
<div data-qfix data-product-id="530956" data-brand="kappahl"></div>
<div data-qfix data-product-id="534008" data-brand="kappahl"></div>
```

### Dynamic product pages (SPA)

If your site is a single-page application where product content loads dynamically, you can re-initialize the widget after updating the DOM:

```js
// After inserting the qfix-repair div into the DOM
window.QFixWidget && window.QFixWidget.init();
```

---

## Customizing the button style

The widget uses scoped CSS classes that won't conflict with your site. To match your brand's design, override the styles:

```css
/* Change button color */
.qfix-widget .qfix-btn {
  background: #0057a8;
}
.qfix-widget .qfix-btn:hover {
  background: #004080;
}

/* Change border radius */
.qfix-widget .qfix-btn {
  border-radius: 0;
}

/* Change font */
.qfix-widget .qfix-btn {
  font-family: "Your Brand Font", sans-serif;
}
```

---

## Troubleshooting

| Problem                     | Cause                                              | Solution                                                  |
|-----------------------------|----------------------------------------------------|------------------------------------------------------------|
| Button doesn't appear       | Product ID not found in the QFix database          | Verify the product ID and brand slug are correct           |
| Button doesn't appear       | Script not loaded                                  | Check browser console for 404 on widget.js                 |
| Button doesn't appear       | `data-product-id` missing                          | Ensure the attribute is set on the div                     |
| Button appears but link fails | QFix booking page URL changed                    | Contact QFix support                                       |

---

## Questions?

Contact the QFix integration team for help with setup or to register your brand.
