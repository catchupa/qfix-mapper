# QFix Repair Redirect — Provider Integration Guide

The simplest way to add QFix repair links to your product pages. No JavaScript widget needed — just a regular link that redirects customers to the correct QFix repair booking page.

## How it works

1. You place a link on your product page pointing to a QFix redirect endpoint
2. When a customer clicks it, the server looks up the product, maps it to QFix categories, and returns a **302 redirect** to the QFix booking page
3. The customer lands directly on the correct page with category, material, and service pre-selected

---

## Endpoints

There are three endpoints, one per service type. Each automatically includes the correct `service_id` in the redirect.

| Endpoint | Service | Redirect example |
|----------|---------|------------------|
| `/<brand>/repair/?productId=<id>` | Repair | `…?category_id=96&material_id=69&service_id=39` |
| `/<brand>/adjustment/?productId=<id>` | Adjust measurements | `…?category_id=96&material_id=69&service_id=40` |
| `/<brand>/care/?productId=<id>` | Washing & care | `…?category_id=96&material_id=69&service_id=42` |

Base URL: `https://kappahl-qfix.fly.dev`

### Parameters

| Parameter   | Location | Required | Description |
|-------------|----------|----------|-------------|
| `brand`     | path     | yes      | Your brand slug (see table below) |
| `productId` | query    | yes      | The product's article number |

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

### Repair link

```html
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008">
  Reparera
</a>
```

### Adjustment link

```html
<a href="https://kappahl-qfix.fly.dev/kappahl/adjustment/?productId=534008">
  Måttanpassa
</a>
```

### Washing & care link

```html
<a href="https://kappahl-qfix.fly.dev/kappahl/care/?productId=534008">
  Skötsel
</a>
```

### All three services for one product

```html
<a href="https://kappahl-qfix.fly.dev/kappahl/repair/?productId=534008">Reparera</a>
<a href="https://kappahl-qfix.fly.dev/kappahl/adjustment/?productId=534008">Måttanpassa</a>
<a href="https://kappahl-qfix.fly.dev/kappahl/care/?productId=534008">Skötsel</a>
```

---

## Response codes

| Status | Meaning |
|--------|---------|
| 302    | Redirect to QFix booking page |
| 400    | Missing `productId` parameter |
| 404    | Unknown brand, product not found, or no repair mapping available |

---

## Live demo

See the redirect links in action on the demo product page:
https://kappahl-qfix.fly.dev/demo/

---

## Comparison: Redirect link vs Widget

| | Redirect link | Widget (`widget.js`) |
|---|---|---|
| **Setup** | Just an `<a>` tag | Script tag + placeholder div |
| **JavaScript required** | No | Yes |
| **Shows availability before click** | No — always visible | Yes — hidden if product not found |
| **API call timing** | On click (server-side) | On page load or click (client-side) |
| **Styling** | Your own CSS | Widget CSS (customizable) |
| **Service type support** | Yes (separate endpoints) | Yes (`data-service` attribute) |

Use the **redirect link** when you want the simplest possible integration with full control over styling. Use the **widget** when you want the button to auto-hide for products without repair support.

---

## Questions?

Contact the QFix integration team for help with setup or to register your brand.
