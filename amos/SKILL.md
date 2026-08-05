---
name: amos
description: >-
  Embed Amos payment methods with iframe client SDKs and the Pay API (any
  backend language: OpenAPI-generated SDK or raw HTTP). Use when integrating
  Amos, mounting card/bank/Google Pay/Apple Pay iframes, wiring
  @amos.com/amos-js / @amos.com/react-amos-js / @amos.com/node, creating
  payment intents or setup intents (save a payment method without charging),
  confirming via embed tokens and onResult, calling pay.amos.com, or debugging
  blank iframes / confirm failures / Signature has expired.
---

# Amos (embed payment methods)

Integrate Amos: **server creates a payment intent or setup intent**, **browser mounts Amos-hosted iframes**, sensitive payment data never enters the merchant DOM.

Same client components for both:

- **Payment intent** — charge now
- **Setup intent** — save a payment method for later (no charge)

The **Pay API HTTP contract** is the source of truth. Backend SDKs (`@amos.com/node`, Ruby, Python, Go, etc.) are OpenAPI-generated clients — or call HTTP directly.

Client packages (current majors): `@amos.com/amos-js` / `@amos.com/react-amos-js` (~0.9.x), `@amos.com/node` (~0.1.x). Prefer the installed package README + types over inventing APIs.

## Architecture

```
Merchant browser                              Amos
─────────────────                             ────
@amos.com/amos-js  ──── postMessage ────►  embed*.amos.com iframe
  or react-amos-js                           (card / bank / google-pay / apple-pay)

Merchant server (any language)
─────────────────────────────
OpenAPI SDK  ─┐
              ├── X-Api-Key ──►  pay*.amos.com
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
| **Render token** | Client | Dashboard render template; encodes `env`, origins, methods, amount range |
| **API key** | Server only | Never ship to the browser |
| **Account ID** | Server / approval | Provided after app approval |

**Env coupling (do not mix):**

| | Sandbox | Production |
|--|---------|------------|
| Dashboard | `dashboard-sandbox.amos.com` | `dashboard.amos.com` |
| Pay API | `https://pay-sandbox.amos.com` | `https://pay.amos.com` |
| Embed | `https://embed-sandbox.amos.com` | `https://embed.amos.com` |

Client SDK picks embed host via `getEmbedOrigin(renderToken)`.

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

```ts
type ConfirmationResult =
  | { status: "succeeded"; intent: "payment"; paymentIntent: /* PaymentIntent */ }
  | { status: "succeeded"; intent: "setup"; setupIntent: /* SetupIntent */ }
  | { status: "incomplete"; reason: "field_errors" | "validation_failed" }
  | { status: "failed"; errorMessage: string };
```

| `status` | Host action |
|----------|-------------|
| `succeeded` | Unlock UI; **verify settlement via webhook / server retrieve** (not proof of funds) |
| `incomplete` | Unlock UI; recoverable — errors shown in iframe; customer can fix and retry |
| `failed` | Unlock UI; show `errorMessage` |

`confirm*` returns `void` — wait on `onResult` for UX. Keep a processing state until `onResult` fires (including `incomplete`).

## Non-express flow (card / bank)

```
mount form (render token) + onResult
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

### React

1. Render `AmosCreditCardPaymentMethodForm` or `AmosBankAccountPaymentMethodForm` with `renderToken` + **`onResult`**.
2. Keep `ref` on the component; pass the **same** `iframeRef` to helpers.
3. On submit: `await validateForm({ iframeRef })` → if false, stop.
4. Call **your** backend → `{ token }`.
5. Immediately `confirmPaymentIntent({ iframeRef, token })` or `confirmSetupIntent(...)`.
6. Unlock / show errors in `onResult` (including `incomplete`).

Optional props: `appearance`, `billingAddressRequirement?: "country" | "full"`, card `additionalFields?: { cardholderName: boolean }`.

Do **not** create the intent in `useEffect` on mount/open.

### Vanilla

Same with `mountAmosCreditCardPaymentMethodForm` / `mountAmosBankAccountPaymentMethodForm`, then `validateForm({ iframe: form.iframe })` and `confirm*({ iframe: form.iframe, token })`.

## Express flow (Google Pay / Apple Pay)

```
mount button → user taps → onInitiatePaymentIntentRequest → your server creates PI → return token → SDK auto-confirms → onResult
```

- Required: `amount` (**string** cents, e.g. `"5000"`), `merchantName`, `onInitiatePaymentIntentRequest`, `onResult`.
- Do **not** call `validateForm` or `confirmPaymentIntent` yourself.
- Map iframe create attributes onto Pay API bodies (`payment_intent`, `customer`) on the server.
- Components: `AmosGooglePayButton` / `AmosApplePayButton` (React) or `mountAmosGooglePayButton` / `mountAmosApplePayButton` (vanilla). Same options shape.
- Apple Pay: Safari uses the native sheet; other browsers use Apple's QR popup. SDK shows a host-page waiting overlay with Cancel while the popup is open — do not reinvent expand/collapse iframe hacks.

## PCI rules (non-negotiable)

- Never collect PAN, CVV, or full bank account numbers in merchant DOM.
- Never put API keys or raw payment method confirm payloads on the client.
- Merchant orchestrates tokens; Amos iframes + embed confirm endpoints handle sensitive data.
- `onResult` is **UX**. Use **webhooks** (or server retrieve) before fulfilling or treating a PM as saved.

## Dashboard prerequisites (blank iframe checklist)

1. Add **parent origin(s)** (exact scheme + host).
2. Create a **render template** with allowed methods.
3. Issue a **render token**.
4. Use an **API key** from the same environment.

Mismatch → blank iframe or method not allowed.

## Common pitfalls

| Symptom / mistake | Fix |
|-------------------|-----|
| Blank iframe | Origin/method not on render template; env mismatch |
| `validateForm` always false | Iframe not ready; 5s timeout; wrong iframe ref |
| Confirm no-ops | Pass mounted `iframe` / `iframeRef`, not the container |
| Wrong confirm helper | Match server endpoint + `confirm*` + `onResult` `intent` |
| Old success/fail callbacks | Use required `onResult` only |
| Spinner stuck after field errors | Handle `status: "incomplete"` — unlock UI |
| **`Signature has expired`** | Create intent on submit/tap; confirm immediately |
| Creating intent on mount/open | Move create into submit path after `validateForm` |
| GPay/Apple Pay amount types | Client prop: string `"5000"`; Pay API: number `5000` |
| Confirming in express flow | Only return token from `onInitiatePaymentIntentRequest` |
| Importing `PaymentIntent` from amos-js | Use `components` from `@amos.com/node` |
| Mixing sandbox key + prod token | Align dashboard, render token, API key, base URL |
| Trusting only `onResult` / postMessage | Verify via webhook or Pay API retrieve |

## Agent workflow

1. Confirm browser stack, **payment vs setup**, methods (including Apple Pay if needed), and **server language / SDK**.
2. Configure Pay API client or raw HTTP; scaffold a route that returns **only** `token`.
3. Scaffold client form/button with **`onResult`**; wire **validate → create → confirm** on submit (or express create-on-tap). Reject create-on-open designs.
4. Handle `incomplete` / `failed` / `succeeded` in `onResult`; remind about dashboard origins and webhooks.
5. Read installed package versions if APIs look unfamiliar — 0.9.x client SDKs use `onResult`, not the old triple-callback API.

## Additional resources

- Pay API contract + SDK discovery: [api-reference.md](api-reference.md)
- HTTP, Node, and client snippets: [examples.md](examples.md)
