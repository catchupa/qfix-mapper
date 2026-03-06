# QFix Widget

Add **Reparera**, **Måttanpassa** and **Skötsel** buttons to your product pages.

When a customer clicks a button, they go directly to the QFix booking page for that product and service.

**Live example:** https://qfix.fly.dev/demo/example/

---

## Add to your page

```html
<!-- Place where you want the buttons -->
<div data-qfix data-product-id="YOUR_PRODUCT_ID" data-brand="YOUR_BRAND"></div>

<!-- Before </body> -->
<script src="https://qfix.fly.dev/widget/v1.js"
        data-api-base="https://qfix.fly.dev" defer></script>
```

Replace:
- `YOUR_PRODUCT_ID` with the product's article number (e.g. `846030`)
- `YOUR_BRAND` with your brand identifier:

| Brand        | `data-brand` value |
|--------------|---------------------|
| KappAhl      | `kappahl`           |
| Gina Tricot  | `ginatricot`        |
| Eton         | `eton`              |
| Nudie Jeans  | `nudie`             |
| Lindex       | `lindex`            |

---

## All buttons or single button

**All three buttons** — leave `data-qfix` empty:

```html
<div data-qfix data-product-id="846030" data-brand="kappahl"></div>
```

**Single button** — set `data-qfix` to the service you want:

```html
<div data-qfix="repair" data-product-id="846030" data-brand="kappahl"></div>
<div data-qfix="adjustment" data-product-id="846030" data-brand="kappahl"></div>
<div data-qfix="care" data-product-id="846030" data-brand="kappahl"></div>
```

Each div renders independently, so you can place them anywhere on the page.

| `data-qfix` value | Button        |
|--------------------|---------------|
| *(empty)*          | All three     |
| `repair`           | Reparera      |
| `adjustment`       | Måttanpassa   |
| `care`             | Skötsel       |

---

## Full page example

```html
<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <title>Product Page</title>
</head>
<body>
  <h1>Hoodie med dragkedja</h1>
  <p>299 kr</p>
  <button>Lagg i varukorgen</button>

  <!-- All QFix buttons -->
  <div data-qfix data-product-id="846030" data-brand="kappahl"></div>

  <!-- Or pick one -->
  <div data-qfix="repair" data-product-id="846030" data-brand="kappahl"></div>

  <script src="https://qfix.fly.dev/widget.js"
          data-api-base="https://qfix.fly.dev"></script>
</body>
</html>
```

---

## Customize the look

Override the default styles with CSS:

```css
/* Button color */
.qfix-widget .qfix-btn {
  background: #0057a8;
}
.qfix-widget .qfix-btn:hover {
  background: #004080;
}

/* Border radius */
.qfix-widget .qfix-btn {
  border-radius: 8px;
}

/* Font */
.qfix-widget .qfix-btn {
  font-family: "Your Font", sans-serif;
}
```

### Built-in themes

Use `data-theme` for quick styling:

| Theme     | Look                               |
|-----------|-------------------------------------|
| *(none)*  | Gray pill buttons (default)         |
| `light`   | Black buttons (for light backgrounds) |
| `dark`    | White buttons (for dark backgrounds)  |

```html
<div data-qfix data-product-id="846030" data-brand="kappahl" data-theme="light"></div>
```

---

## Versioning

Always use the versioned URL in production. Versioned URLs are stable and won't change behavior.

| URL               | Behavior                                    |
|-------------------|---------------------------------------------|
| `/widget/v1.js`   | Stable — pinned to version 1 (recommended)  |
| `/widget.js`      | Always serves the latest version            |

---

## Single-page apps

Re-initialize after dynamically adding widget elements:

```js
window.QFixWidget.init();
```

---

## Questions?

Contact the QFix team for help or to register your products.
