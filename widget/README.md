# QFix Widget

Add **Reparera**, **Mattanpassa** and **Skotsel** buttons to your product pages.

When a customer clicks a button, they go directly to the QFix booking page for that product and service.

**Live example:** https://qfix.fly.dev/demo/example/

---

## Add to your page

```html
<!-- Place where you want the buttons -->
<div data-qfix data-product-id="YOUR_PRODUCT_ID" data-brand="YOUR_BRAND"></div>

<!-- Before </body> -->
<script src="https://qfix.fly.dev/widget.js"
        data-api-base="https://qfix.fly.dev"></script>
```

Replace:
- `YOUR_PRODUCT_ID` with the product's article number (e.g. `846030`)
- `YOUR_BRAND` with your brand identifier:

| Brand        | `data-brand` value |
|--------------|--------------------|
| KappAhl      | `kappahl`          |
| Gina Tricot  | `ginatricot`       |
| Eton         | `eton`             |
| Nudie Jeans  | `nudie`            |
| Lindex       | `lindex`           |

That's it. The widget:
- Fetches the available services for the product
- Renders buttons for each service (Reparera, Mattanpassa, Skotsel)
- Opens the QFix booking page in a new tab when clicked
- Shows nothing if the product isn't found

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

  <!-- QFix buttons -->
  <div data-qfix data-product-id="846030" data-brand="kappahl"></div>

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

## Single-page apps

Re-initialize after dynamically adding widget elements:

```js
window.QFixWidget.init();
```

---

## Questions?

Contact the QFix team for help or to register your products.
