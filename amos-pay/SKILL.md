---
name: amos-pay
description: >-
  Embed Amos payment methods with iframe client SDKs and the Pay API (any
  backend language: OpenAPI-generated SDK or raw HTTP). Use when integrating
  Amos Pay, mounting card/bank/Google Pay iframes, wiring @amos.com/amos-js /
  @amos.com/react-amos-js, creating payment intents or setup intents (save a
  payment method without charging), confirming via embed tokens, calling
  pay.amos.com, or debugging blank iframes / confirm failures / Signature has
  expired.
---

# Amos Pay (embed payment methods)

Integrate Amos Pay: **server creates a payment intent or setup intent**, **browser mounts Amos-hosted iframes**, sensitive payment data never enters the merchant DOM.

Use the same client components for both:

- **Payment intent** — charge the customer now
- **Setup intent** — save a payment method for later (no charge)

The **Pay API HTTP contract** is the source of truth. Backend SDKs (`@amos.com/node`, Ruby, Python, Go, etc.) are OpenAPI-generated clients over that same contract — or the merchant can call HTTP directly.

## Architecture

```
Merchant browser                              Amos
─────────────────                             ────
@amos.com/amos-js  ──── postMessage ────►  embed*.amos.com iframe
  or react-amos-js                           (card / bank / google-pay)

Merchant server (any language)
─────────────────────────────
OpenAPI SDK  ─┐
              ├── X-Api-Key ──►  pay*.amos.com
raw HTTP     ─┘
  POST /payment_intents | /setup_intents  →  EmbedToken { token, ttl }
```

| Layer                         | Role                                                               |
| ----------------------------- | ------------------------------------------------------------------ |
| **Pay API**                   | Server-side REST API; create intents, customers, retrieve status   |
| **Backend SDK / HTTP**        | How the merchant server talks to the Pay API (secrets stay here)   |
| `@amos.com/amos-js`           | Vanilla / framework-agnostic iframe mounts + messaging             |
| `@amos.com/react-amos-js`     | React wrappers around amos-js                                      |
| Embed app (`embed*.amos.com`) | Iframe **content** the client SDKs load (not a partner dependency) |

Docs: [docs.amos.com](https://docs.amos.com). Prefer `@amos.com/react-amos-js` in React apps; otherwise `@amos.com/amos-js`.

## Two tokens (do not conflate)

| Token            | When                                             | Where                             | Used for                                         |
| ---------------- | ------------------------------------------------ | --------------------------------- | ------------------------------------------------ |
| **Render token** | Before mount (dashboard template / env)          | Client; iframe `?token=`          | Allowed origins, methods, env; mounts the iframe |
| **Embed token**  | From `POST /payment_intents` or `/setup_intents` | Server → browser only for confirm | `Authorization: Embed …` on confirm              |

The render token loads the form. The embed token authorizes **one confirm**. Create response is `EmbedToken { token, ttl }` — `ttl` is typically ~3600s. After that, Pay API returns errors like `{"errors":{"base":["Signature has expired"]}}`.

## Intent timing (required pattern)

**Create the intent on submit (or GPay tap), then confirm immediately with that fresh embed token.** Do not create the intent when the form mounts or the dialog opens.

```
✅ mount iframe (render token only)
   → user fills fields (may take a long time — OK)
   → validateForm
   → POST create intent  →  { token }   ← mint embed token HERE
   → confirm*({ token })               ← use it RIGHT AWAY

❌ open form → create intent → user types for 20+ min → confirm(stale token)
   → Signature has expired
```

Same rule for **setup intents** and **payment intents**. Prefetching an intent “to warm up” the Save button is an anti-pattern.

## Credentials

| Credential       | Where             | Notes                                                                                         |
| ---------------- | ----------------- | --------------------------------------------------------------------------------------------- |
| **Render token** | Client            | From dashboard render template; encodes `env`, allowed origins, payment methods, amount range |
| **API key**      | Server only       | Never ship to the browser                                                                     |
| **Account ID**   | Server / approval | Provided after app approval                                                                   |

**Env coupling (do not mix):**

|           | Sandbox                          | Production               |
| --------- | -------------------------------- | ------------------------ |
| Dashboard | `dashboard-sandbox.amos.com`     | `dashboard.amos.com`     |
| Pay API   | `https://pay-sandbox.amos.com`   | `https://pay.amos.com`   |
| Embed     | `https://embed-sandbox.amos.com` | `https://embed.amos.com` |

Client SDK picks embed host from render token via `getEmbedOrigin(renderToken)`.

## Decision tree

1. **Browser stack:** React → `@amos.com/react-amos-js`. Else → `@amos.com/amos-js`.
2. **Intent:** Charge now → **payment intent**. Save PM only → **setup intent**.
3. **Method:** Card/bank → non-express. Google Pay → express (payment intents).
4. **Server:** Add a route that creates the intent via Pay API (SDK or HTTP) and returns only `token` from `EmbedToken` to the browser — called from the submit/tap path, not page load.

## Server: Pay API (SDK or HTTP)

Every backend does the same three things:

1. Authenticate with `X-Api-Key` + `X-Api-Version` (see [api-reference.md](api-reference.md)).
2. `POST /payment_intents` or `POST /setup_intents` with the documented JSON body.
3. Read `token` from the `EmbedToken` response and return it to the browser (never the API key).

### Using an OpenAPI-generated SDK

Official language SDKs wrap the same OpenAPI spec. When the project has (or will install) a generated client:

1. **Find the client entrypoint** — package README, `create*Client`, `Client`, `Amos::Client`, etc.
2. **Configure base URL + default headers** for sandbox or production; set `X-Api-Key` and `X-Api-Version` once on the client.
3. **Map operations by path/operationId**, not by invented method names:
   - `POST /payment_intents` → create payment intent → returns `EmbedToken`
   - `POST /setup_intents` → create setup intent → returns `EmbedToken`
   - `POST /customers` → create customer (optional)
4. **Use generated request/response types** when available; do not hand-roll field names that disagree with the OpenAPI schemas.
5. **Send `Idempotency-Key` on POSTs** if the client supports middleware/interceptors or per-request headers.
6. If the SDK's method names are unclear, open its generated paths/operations types or the OpenAPI spec and search for the path string.

`@amos.com/node` is one such client (TypeScript, `openapi-fetch`). Other languages follow the same mapping — only call syntax changes.

### Using raw HTTP

Same contract without a client library: `POST` JSON to `{baseUrl}/payment_intents` (or `/setup_intents`) with the auth headers. Parse JSON; take `token`. Full shapes in [api-reference.md](api-reference.md); copy-paste in [examples.md](examples.md).

### Merchant route contract (browser ↔ your server)

Your app's HTTP API can use any shape. The browser only needs the **embed JWT string**. Common patterns:

```http
POST /api/payment-intents  →  { "token": "<EmbedToken.token>" }
POST /api/setup-intents    →  { "token": "<EmbedToken.token>" }
```

Call these routes from the **submit / GPay initiate** handler. Do not create intents on page load or form-open and stash the token for later.

Do not proxy raw Pay API error bodies that leak internals; map to safe client errors.

## Non-express flow (card / bank)

Same UI for payment and setup intents; only the server endpoint and confirm helper differ.

```
mount form (render token)
  → user fills iframe
  → validateForm
  → your server creates intent   ← embed token minted here
  → confirm*({ token })          ← confirm immediately
  → success/fail callbacks
```

|                  | Payment intent                         | Setup intent                         |
| ---------------- | -------------------------------------- | ------------------------------------ |
| Server           | `POST /payment_intents`                | `POST /setup_intents`                |
| Client confirm   | `confirmPaymentIntent`                 | `confirmSetupIntent`                 |
| Success callback | `onPaymentIntentConfirmationSucceeded` | `onSetupIntentConfirmationSucceeded` |

### React

1. Render `AmosCreditCardPaymentMethodForm` or `AmosBankAccountPaymentMethodForm` with `renderToken` + `onConfirmationFailed` (+ the matching success callback).
2. Keep `ref` on the component; pass the **same** `iframeRef` to helpers.
3. On submit: `await validateForm({ iframeRef })` → if false, stop.
4. Call **your** backend → receive `{ token }`.
5. Immediately `confirmPaymentIntent({ iframeRef, token })` or `confirmSetupIntent(...)`.
6. Outcomes arrive via callbacks (`confirm*` returns `void`). Keep processing until success/fail.

Do **not** create the intent in a `useEffect` on mount/open and reuse that `token` on Save.

### Vanilla

Same with `mountAmosCreditCardPaymentMethodForm` / `mountAmosBankAccountPaymentMethodForm`, then `validateForm({ iframe: form.iframe })` and the matching `confirm*` helper with `{ iframe: form.iframe, token }`.

## Express flow (Google Pay)

```
mount button → user taps GPay → onInitiatePaymentIntentRequest → your server creates PI → return token → client SDK auto-confirms
```

Create-on-tap is the same timing rule: the embed token is minted in the initiate handler and consumed immediately by the SDK.

- Required: `amount` (**string** cents, e.g. `"5000"`), `merchantName`, `onInitiatePaymentIntentRequest`, `onPaymentIntentConfirmationSucceeded`, `onConfirmationFailed`.
- Do **not** call `validateForm` or `confirmPaymentIntent` yourself.
- Map iframe create attributes onto Pay API bodies (`payment_intent`, `customer`) on the server — field names may differ from the browser callback payload.

## PCI rules (non-negotiable)

- Never collect PAN, CVV, or full bank account numbers in merchant DOM/forms.
- Never put API keys or raw payment method confirm payloads on the client.
- Merchant orchestrates tokens; Amos iframes + embed confirm endpoints handle sensitive data.
- Iframe success callbacks are **UX**. Use **webhooks** (or server retrieve) as source of truth before fulfilling an order or treating a payment method as saved.

## Dashboard prerequisites (blank iframe checklist)

1. Add **parent origin(s)** (exact scheme + host).
2. Create a **render template** with allowed methods.
3. Issue a **render token**.
4. Use an **API key** from the same environment.

Mismatch → blank iframe or method not allowed.

## Common pitfalls

| Symptom / mistake                               | Fix                                                                                                                        |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Blank iframe                                    | Origin/method not on render template; env mismatch                                                                         |
| `validateForm` always false                     | Iframe not ready; 5s timeout; wrong iframe ref                                                                             |
| Confirm no-ops                                  | Pass mounted `iframe` / `iframeRef`, not the container                                                                     |
| Wrong confirm helper                            | Payment vs setup: match server endpoint, `confirm*`, and success callback                                                  |
| **`Signature has expired` / embed JWT expired** | **Create intent on submit/tap, not on form open; confirm immediately. Do not hold embed tokens across long idle periods.** |
| Creating intent on mount/open                   | Move create into the submit path after `validateForm`                                                                      |
| GPay amount types                               | Client prop: string `"5000"`; Pay API: number `5000`                                                                       |
| Success never fires                             | `confirm*` is fire-and-forget — wait on callbacks                                                                          |
| Confirming in GPay flow                         | Only return token from `onInitiatePaymentIntentRequest`                                                                    |
| Inventing SDK method names                      | Look up OpenAPI path / operationId in the generated client                                                                 |
| Mixing sandbox key + prod token                 | Align dashboard, render token, API key, base URL                                                                           |
| Trusting only postMessage                       | Verify via webhook or Pay API retrieve                                                                                     |
| Blaming render token for expiry                 | Render tokens often have no short `exp`; check whether a **stale embed token** was confirmed late                          |

## Agent workflow

1. Confirm browser stack, **payment vs setup intent**, payment methods, and **server language / whether an Amos API SDK is already in the project**.
2. If an OpenAPI SDK is present: configure it and call the create-intent operation. If not: use raw HTTP (or add the language's official SDK if the user wants one).
3. Scaffold a merchant server route that returns **only** `token`.
4. Scaffold the client form/button; wire **validate → create → confirm** in that order on submit (or express create-on-tap for GPay). Reject any create-on-open / create-on-mount + later confirm design.
5. Remind about dashboard origins/templates and webhooks.
6. Do not invent Apple Pay client mounts unless the installed client SDK documents them.

## Additional resources

- Pay API contract + SDK discovery: [api-reference.md](api-reference.md)
- HTTP, Node, and client snippets: [examples.md](examples.md)
