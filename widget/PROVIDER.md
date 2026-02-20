# QFix Repair Redirect — Provider Integration Guide

The simplest way to add QFix repair links to your product pages. No JavaScript widget needed — just a regular link that redirects customers to the correct QFix repair booking page.

## How it works

1. You place a link on your product page pointing to the QFix redirect endpoint
2. When a customer clicks it, the server looks up the product, maps it to QFix repair categories, and returns a **302 redirect** to the QFix booking page
3. The customer lands directly on the correct repair page with category and material pre-selected

---

## Endpoint

```
GET https://kappahl-qfix.fly.dev/<brand>/repair/?productId=<product_id>
```

| Parameter   | Location | Required | Description |
|-------------|----------|----------|-------------|
| `brand`     | path     | yes      | Your brand slug (see table below) |
| `productId` | query    | yes      | The product's article number |
| `service`   | query    | no       | Service type: `repair`, `adjustment`, or `washing` |

### Brand slugs

| Brand        | Slug          |
|--------------|---------------|
| KappAhl      | `kappahl`     |
| Gina Tricot  | `ginatricot`  |
| Eton         | `eton`        |
| Nudie Jeans  | `nudie`       |
| Lindex       | `lindex`      |

---

## Examples

### Basic repair link

```html
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008">
  Reparera detta plagg
</a>
```

The customer is redirected to something like:
```
https://kappahl.dev.qfixr.me/sv/?category_id=93&material_id=69
```

### With a specific service

```html
<!-- Repair -->
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008&service=repair">
  Reparera
</a>

<!-- Adjust measurements -->
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008&service=adjustment">
  Måttanpassa
</a>

<!-- Washing and care -->
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008&service=washing">
  Skötsel
</a>
```

When `service` is specified, a `service_id` parameter is appended to the redirect URL:
```
https://kappahl.dev.qfixr.me/sv/?category_id=93&material_id=69&service_id=39
```

### All three services for one product

```html
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008&service=repair">Reparera</a>
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008&service=adjustment">Måttanpassa</a>
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008&service=washing">Skötsel</a>
```

---

## Response codes

| Status | Meaning |
|--------|---------|
| 302    | Redirect to QFix booking page |
| 400    | Missing `productId` parameter |
| 404    | Unknown brand, product not found, or no repair mapping available |

---

## Comparison: Redirect link vs Widget

| | Redirect link | Widget (`widget.js`) |
|---|---|---|
| **Setup** | Just an `<a>` tag | Script tag + placeholder div |
| **JavaScript required** | No | Yes |
| **Shows availability before click** | No — always visible | Yes — hidden if product not found |
| **API call timing** | On click (server-side) | On page load or click (client-side) |
| **Styling** | Your own CSS | Widget CSS (customizable) |
| **Service type support** | Yes (`&service=`) | Yes (`data-service`) |

Use the **redirect link** when you want the simplest possible integration with full control over styling. Use the **widget** when you want the button to auto-hide for products without repair support.

---

## Questions?

Contact the QFix integration team for help with setup or to register your brand.
