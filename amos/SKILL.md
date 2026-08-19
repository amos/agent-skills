---
name: amos
description: >-
  Embed Amos payment methods with iframe client SDKs and the Pay API (any
  backend language: OpenAPI-generated SDK or raw HTTP). Use when integrating
  Amos, mounting card/bank/Google Pay/Apple Pay iframes, wiring
  @amos.com/amos-js / @amos.com/react-amos-js / @amos.com/node, creating
  payment intents or setup intents (save a payment method without charging),
  confirming via embed tokens and onResult, calling api.amos.com, resetForm,
  onValidityChange, payment method tabs, wallet buttonProps / iframeProps, or
  debugging blank iframes / confirm failures / Signature has expired.
---

# Amos (embed payment methods)

Integrate Amos: **server creates a payment intent or setup intent**, **browser mounts Amos-hosted iframes**, sensitive payment data never enters the merchant DOM.

Same client components for both:

- **Payment intent** — charge now
- **Setup intent** — save a payment method for later (no charge)

The **Pay API HTTP contract** is the source of truth. Backend SDKs (`@amos.com/node`, Ruby, Python, Go, etc.) are OpenAPI-generated clients — or call HTTP directly.

Client packages (current majors): `@amos.com/amos-js` (~0.9.15), `@amos.com/react-amos-js` (~0.9.14), `@amos.com/node` (~0.1.x, peer `>=0.1.39`). `@amos.com/node` is a **peer dependency** of both client SDKs (install it for OpenAPI types even in browser-only TypeScript). Prefer the installed package README + types over inventing APIs.

## Architecture

```
Merchant browser                              Amos
─────────────────                             ────
@amos.com/amos-js  ──── postMessage ────►  embed*.amos.com iframe
  or react-amos-js                           (card / bank / google-pay / apple-pay)

Merchant server (any language)
─────────────────────────────
OpenAPI SDK  ─┐
              ├── X-Api-Key ──►  api*.amos.com
raw HTTP     ─┘
  POST /payment_intents | /setup_intents  →  EmbedToken { token, ttl }
```

| Layer | Role |
|-------|------|
| **Pay API** | Server-side REST; create intents, customers, retrieve status |
| **Backend SDK / HTTP** | Merchant server → Pay API (secrets stay here) |
| `@amos.com/amos-js` | Vanilla iframe mounts + messaging |
| `@amos.com/react-amos-js` | React wrappers (re-exports amos-js) |
| Embed app (`embed*.amos.com`) | Iframe **content** (not a partner dependency) |

Docs: [docs.amos.com](https://docs.amos.com). Prefer `@amos.com/react-amos-js` in React; otherwise `@amos.com/amos-js`.

OpenAPI schema types (`PaymentIntent`, `EmbedToken`, etc.) come from `@amos.com/node` as `components["schemas"]["…"]` — client SDKs no longer re-export those aliases.

## Two tokens (do not conflate)

| Token | When | Where | Used for |
|-------|------|--------|----------|
| **Render token** | Before mount (dashboard template / env) | Client; iframe `?token=` | Allowed origins, methods, env; mounts the iframe |
| **Embed token** | From `POST /payment_intents` or `/setup_intents` | Server → browser only for confirm | `Authorization: Embed …` on confirm |

Render token loads the form. Embed token authorizes **one confirm**. Create response is `EmbedToken { token, ttl }` — `ttl` typically ~3600s. After that: `{"errors":{"base":["Signature has expired"]}}`.

## Intent timing (required pattern)

**Create the intent on submit (or express tap), then confirm immediately with that fresh embed token.** Do not create when the form mounts or the dialog opens.

```
✅ mount iframe (render token only)
   → user fills fields (may take a long time — OK)
   → validateForm
   → POST create intent  →  { token }   ← mint embed token HERE
   → confirm*({ token })               ← use it RIGHT AWAY
   → onResult({ status })              ← unlock UI here

❌ open form → create intent → user types for 20+ min → confirm(stale token)
   → Signature has expired
```

Same rule for setup and payment intents. Prefetching an intent “to warm up” Save is an anti-pattern.

## Credentials

| Credential | Where | Notes |
|------------|--------|------|
| **Render token** | Client | Dashboard render template; encodes `env`, origins, methods, amount range, `billing_address_options` |
| **API key** | Server only | Never ship to the browser |
| **Account ID** | Server / approval | Provided after app approval |

**Env coupling (do not mix):**

| | Sandbox | Production |
|--|---------|------------|
| Dashboard | `dashboard-sandbox.amos.com` | `dashboard.amos.com` |
| Pay API | `https://api-sandbox.amos.com` | `https://api.amos.com` |
| Embed | `https://embed-sandbox.amos.com` | `https://embed.amos.com` |

`@amos.com/node` exports `AMOS_API_BASE_URL_SANDBOX` / `AMOS_API_BASE_URL_PRODUCTION` and `AMOS_API_VERSION`. Do not use the old `PAY_API_*` names or `pay.amos.com` hosts.

Client SDK picks embed host via `getEmbedOrigin(renderToken)`. Render templates also encode billing geography (`billing_address_options`: `us_only` + `allowed_states`, or `international` + `allowed_countries`). Addresses outside that set are rejected.

## Decision tree

1. **Browser:** React → `@amos.com/react-amos-js`. Else → `@amos.com/amos-js`.
2. **Intent:** Charge now → payment intent. Save PM only → setup intent.
3. **Method:** Card/bank → non-express. Google Pay / Apple Pay → express (payment intents).
4. **Server:** Route that creates the intent (SDK or HTTP) and returns only `token` — called from submit/tap, not page load.

## Server: Pay API (SDK or HTTP)

1. Authenticate with `X-Api-Key` + `X-Api-Version` (see [api-reference.md](api-reference.md)).
2. `POST /payment_intents` or `POST /setup_intents` with the documented JSON body.
3. Read `token` from `EmbedToken` and return it to the browser (never the API key).

### Using an OpenAPI-generated SDK

1. Find the client entrypoint (`createPayApiClient`, `Client`, etc.).
2. Configure base URL + `X-Api-Key` / `X-Api-Version`.
3. Map by path/operationId:
   - `POST /payment_intents` → `EmbedToken`
   - `POST /setup_intents` → `EmbedToken`
   - `POST /customers` → `Customer`
4. Use generated request/response types; do not invent field names.
5. Send `X-Idempotency-Key` when the OpenAPI documents it (e.g. refunds, payouts, voids).
6. If method names are unclear, search the generated paths for the path string.

`@amos.com/node` is the TypeScript client (`openapi-fetch`). Other languages: same contract, different call syntax.

### Merchant route contract

```http
POST /api/payment-intents  →  { "token": "<EmbedToken.token>" }
POST /api/setup-intents    →  { "token": "<EmbedToken.token>" }
```

Call from **submit / express initiate**. Do not create on page load. Map Pay API errors to safe client messages.

## `onResult` (required — do not use old callbacks)

All mounts/components take a single required **`onResult: (result: ConfirmationResult) => void`**.

Removed (do not use): `onPaymentIntentConfirmationSucceeded`, `onSetupIntentConfirmationSucceeded`, `onConfirmationFailed`.

`onResult` is how **your page** learns that an interactive confirm attempt finished so you can run **your own UX** (stop spinners, show a thank-you screen, show a top-level error banner, enable “pay again”). It is **not** settlement proof — verify charge / saved PM via webhook or server retrieve before fulfilling.

### Where errors appear vs what the host does

| Situation | Where the customer sees it | What `onResult` tells the host |
|-----------|----------------------------|--------------------------------|
| Missing/invalid card or bank fields | **Under the fields inside the Amos iframe** (before or during confirm) | `status: "incomplete"`, `reason: "field_errors"` — unlock UI; **do not** duplicate field errors on the host page; customer fixes in the iframe and retries |
| Recoverable confirm validation | Same — inline in the iframe | `status: "incomplete"`, `reason: "validation_failed"` — same host action |
| Non-recoverable / API failure | Host page (or toast) via **`errorMessage`** | `status: "failed"` — show `errorMessage`; unlock UI |
| Interactive confirm succeeded | Your success UX (thank-you, redirect, etc.) | `status: "succeeded"` with `paymentIntent` or `setupIntent` — then **verify on your server** before treating as paid or saved |

Field-level messaging stays in the iframe. The host’s job on `incomplete` is to **unlock** (e.g. re-enable the submit button), not to render per-field errors.

```ts
type ConfirmationResult =
  | { status: "succeeded"; intent: "payment"; paymentIntent: /* PaymentIntent */ }
  | { status: "succeeded"; intent: "setup"; setupIntent: /* SetupIntent */ }
  | { status: "incomplete"; reason: "field_errors" | "validation_failed" }
  | { status: "failed"; errorMessage: string };
```

| `status` | Host action |
|----------|-------------|
| `succeeded` | Run success UX from `onResult`; **verify settlement via webhook / server retrieve** (not proof of funds) |
| `incomplete` | Unlock UI only — errors already shown under iframe fields; customer can fix and retry |
| `failed` | Unlock UI; show `errorMessage` on the host page |

`confirm*` returns `void` — wait on `onResult` for UX. Keep a processing state until `onResult` fires (including `incomplete`).

To clear fields and API errors without remounting (e.g. after `succeeded` when starting another payment, or when the customer wants a fresh form), call **`resetForm`** with the same iframe ref/element after `onResult`.

## `onValidityChange` (card / bank)

Optional. The iframe posts `{ isValid }` when required fields become valid or invalid (**no PCI data**). Use it to enable/disable the host Pay/Save button. Still call `validateForm` on submit — `onValidityChange` is button UX, not a substitute for the submit gate.

## Non-express flow (card / bank)

```
mount form (render token) + onResult [+ onValidityChange]
  → user fills iframe
  → validateForm
  → your server creates intent   ← embed token minted here
  → confirm*({ token })          ← confirm immediately
  → onResult
```

| | Payment intent | Setup intent |
|--|----------------|--------------|
| Server | `POST /payment_intents` | `POST /setup_intents` |
| Client confirm | `confirmPaymentIntent` | `confirmSetupIntent` |
| Success in `onResult` | `intent: "payment"` | `intent: "setup"` |

Card/bank **mount helpers and React components** show a field-shaped **loading skeleton** immediately (sized from `appearance`, `additionalFields`, `billingAddressRequirement`) and replace it with the iframe when appearance is ready. Do not invent a host-page placeholder or hide the mount until “ready.” Express buttons (Google Pay / Apple Pay) do not use this skeleton.

### Tabs / multiple methods (keep mounted)

If checkout switches between methods (card, bank, etc.) with tabs or similar UI, **mount every form you offer up front** and hide inactive ones with CSS. Do not mount only the selected tab.

Unmounting on tab change reloads the iframe and re-shows the skeleton. Keeping all mounts in the DOM (visually hidden when inactive) means a tab switch is instant.

```tsx
{/* ✅ always render; hide inactive panels */}
<div hidden={method !== "card"}><AmosCreditCardPaymentMethodForm … /></div>
<div hidden={method !== "bank"}><AmosBankAccountPaymentMethodForm … /></div>

{/* ❌ remounts on every switch */}
{method === "card" ? <AmosCreditCardPaymentMethodForm … /> : <AmosBankAccountPaymentMethodForm … />}
```

Same for vanilla: call each `mount*` once; toggle `hidden` (or equivalent CSS) on the containers. Confirm/validate against the **visible** method’s iframe.

### React

1. Render `AmosCreditCardPaymentMethodForm` or `AmosBankAccountPaymentMethodForm` with `renderToken` + **`onResult`**. The component mounts into a wrapper `div`; **`ref` still points at the iframe**.
2. Keep `ref` on the component; pass the **same** `iframeRef` to helpers (not the wrapper).
3. Optional: `onValidityChange={({ isValid }) => …}` to enable/disable the submit button.
4. On submit: `await validateForm({ iframeRef })` → if false, stop.
5. Call **your** backend → `{ token }`.
6. Immediately `confirmPaymentIntent({ iframeRef, token })` or `confirmSetupIntent(...)`.
7. Unlock in `onResult` — on `incomplete`, only re-enable the button (field errors are in the iframe); on `failed`, show `errorMessage`; on `succeeded`, run your success UX then verify server-side.
8. Optional: `resetForm({ iframeRef })` after `onResult` when clearing the form for another attempt (without destroying the mount).

Optional props: `appearance` (**card/bank only**), `onValidityChange`, `billingAddressRequirement?: "country" | "full"` (`country` collects country/region and postal for CA / PR / GB / US; `full` is street address + Smarty autocomplete), card `additionalFields?: { cardholderName: boolean }`.

Do **not** create the intent in `useEffect` on mount/open.

### Vanilla

Same with `mountAmosCreditCardPaymentMethodForm` / `mountAmosBankAccountPaymentMethodForm` (skeleton is automatic), then `validateForm({ iframe: form.iframe })` and `confirm*({ iframe: form.iframe, token })`. Pass `onValidityChange` on mount. Use `resetForm({ iframe: form.iframe })` to clear fields/errors without remounting.

## Express flow (Google Pay / Apple Pay)

```
mount button → user taps → onInitiatePaymentIntentRequest → your server creates PI → return token → SDK auto-confirms → onResult
```

- Required: `amount` (**string** major-currency decimal, e.g. `"50.00"` for $50.00), `merchantName`, `onInitiatePaymentIntentRequest`, `onResult`. The iframe converts that string to cents in `paymentIntentCreateAttributes.amount` — forward those attributes to `POST /payment_intents` as-is.
- Do **not** call `validateForm` or `confirmPaymentIntent` yourself.
- Map iframe create attributes onto Pay API bodies (`payment_intent`, `customer`) on the server.
- Components: `AmosGooglePayButton` / `AmosApplePayButton` (React) or `mountAmosGooglePayButton` / `mountAmosApplePayButton` (vanilla).
- Wallet buttons do **not** take `appearance`.
- **Layout:** the branded button fills the iframe. `height` is a CSS length (default `"48px"`). Size the **mount slot** (container width), not the button. Compact Google Pay: `buttonProps: { buttonSizeMode: "static", style: { width: "240px" } }`.
- **`buttonProps`:** native button options. Google Pay omitted fields keep `buttonType: "plain"` and `buttonSizeMode: "fill"` (`buttonColor`, `buttonBorderType`, `buttonLocale`, `style`, …). Apple Pay omitted fields keep `buttonstyle: "black"`, `type: "plain"`, `locale: "en-US"` (`style.width` also sets `--apple-pay-button-width` unless you set that custom property).
- **Host iframe:** React `iframeProps` (`style`, `className`, `id`). Vanilla `iframeClassName` / `iframeStyle`. Use CSS values with units (`{ borderRadius: "8px" }`).
- **Removed (do not use):** `fullWidth`, top-level `buttonType` / `buttonstyle` / `type` / `style` / `buttonStyle`. Those belong in `buttonProps` (and `height` for painted height).
- Apple Pay: Safari uses the native sheet; other browsers use Apple's QR popup. SDK shows a host-page waiting overlay with Cancel while the popup is open — do not reinvent expand/collapse iframe hacks.

## PCI rules (non-negotiable)

- Never collect PAN, CVV, or full bank account numbers in merchant DOM.
- Never put API keys or raw payment method confirm payloads on the client.
- Merchant orchestrates tokens; Amos iframes + embed confirm endpoints handle sensitive data.
- `onResult` is **UX**. Use **webhooks** (or server retrieve) before fulfilling or treating a PM as saved.

## Dashboard prerequisites (blank iframe checklist)

1. Add **parent origin(s)** (exact scheme + host).
2. Create a **render template** with allowed methods (and billing geography).
3. Issue a **render token**.
4. Use an **API key** from the same environment.

Mismatch → blank iframe or method not allowed.

## Common pitfalls

| Symptom / mistake | Fix |
|-------------------|-----|
| Blank iframe | Origin/method not on render template; env mismatch |
| Billing address rejected | Render template `billing_address_options` (`us_only` / `international`) |
| `validateForm` always false | Iframe not ready; 5s timeout; wrong iframe ref |
| Confirm no-ops | Pass mounted `iframe` / `iframeRef`, not the container / React wrapper `div` |
| Custom card/bank loading UI | SDK already shows a field skeleton; don’t overlay or hide the mount |
| Tab switch remounts / flashes skeleton | Keep all method forms mounted; hide inactive tabs with CSS (`hidden`) |
| Wrong confirm helper | Match server endpoint + `confirm*` + `onResult` `intent` |
| Old success/fail callbacks | Use required `onResult` only |
| Spinner stuck after field errors | Handle `status: "incomplete"` — unlock UI |
| Need to clear form after success/retry | `resetForm({ iframeRef })` / `resetForm({ iframe })` — do not remount unless needed |
| Pay/Save button never enables | Wire `onValidityChange({ isValid })`; still `validateForm` on submit |
| **`Signature has expired`** | Create intent on submit/tap; confirm immediately |
| Creating intent on mount/open | Move create into submit path after `validateForm` |
| GPay/Apple Pay amount types | Client prop: major-currency string `"50.00"`; Pay API / `paymentIntentCreateAttributes.amount`: number `5000` (cents). Passing `"5000"` to the button charges $5,000. |
| `fullWidth` / top-level `buttonType` / `buttonStyle` | Breaking: use `height` + `buttonProps` + React `iframeProps` (vanilla `iframeStyle`) |
| Confirming in express flow | Only return token from `onInitiatePaymentIntentRequest` |
| Importing `PaymentIntent` from amos-js | Use `components` from `@amos.com/node` |
| Mixing sandbox key + prod token | Align dashboard, render token, API key, base URL |
| `PAY_API_*` / `pay.amos.com` | Current `@amos.com/node`: `AMOS_API_*` + `api.amos.com` / `api-sandbox.amos.com` |
| Trusting only `onResult` / postMessage | Verify via webhook or Pay API retrieve |

## Agent workflow

1. Confirm browser stack, **payment vs setup**, methods (including Apple Pay if needed), and **server language / SDK**.
2. Configure Pay API client or raw HTTP; scaffold a route that returns **only** `token`.
3. Scaffold client form/button with **`onResult`**; wire **validate → create → confirm** on submit (or express create-on-tap). Reject create-on-open designs. On card/bank, wire **`onValidityChange`** to the host button. If the UI uses method tabs, mount every form and hide inactive ones with CSS.
4. Handle `incomplete` / `failed` / `succeeded` in `onResult`; remind about dashboard origins and webhooks (`payment_intent.succeeded` / `setup_intent.succeeded`).
5. Read installed package versions if APIs look unfamiliar — 0.9.15+ client SDKs use `onResult`, `onValidityChange`, `resetForm`, a card/bank loading skeleton, and wallet `height` / `buttonProps` / `iframeProps` (not `fullWidth` or top-level `buttonType` / `buttonStyle`).

## Additional resources

- Pay API contract + SDK discovery: [api-reference.md](api-reference.md)
- HTTP, Node, and client snippets: [examples.md](examples.md)
