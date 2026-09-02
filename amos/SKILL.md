---
name: amos
description: >-
  Embed Amos payment methods with iframe client SDKs and the Pay API (any
  backend language: OpenAPI-generated SDK or raw HTTP). Use when integrating
  Amos, mounting card/bank/Google Pay/Apple Pay iframes, wiring
  @amos.com/amos-js / @amos.com/react-amos-js / @amos.com/node, creating
  payment intents or setup intents (save a payment method without charging),
  awaiting confirmPayment / confirmSetup and their result types, onConfirm for
  wallets, calling api.amos.com, resetForm, onResult, onValidityChange,
  onCardBrandChanged, defaultValues, focusField, Enter key / host form submit /
  FORM_SUBMIT_REQUEST, payment method tabs, wallet buttonProps / iframeProps,
  Plaid Embedded Institution Search / Plaid Link / ACH verification /
  requireAchVerification / intent, appearance fonts / rules / --font-family,
  onEscapeKeyPressed, isConfirmTimeout / confirm timeout, render token
  verification, or debugging blank iframes / confirm failures / Signature has
  expired.
---

# Amos (embed payment methods)

Integrate Amos: **server creates a payment intent or setup intent**, **browser mounts Amos-hosted iframes**, sensitive payment data never enters the merchant DOM.

Same client components for both:

- **Payment intent** — charge now
- **Setup intent** — save a payment method for later (no charge)

The **Pay API HTTP contract** is the source of truth. Backend SDKs (`@amos.com/node`, Ruby, Python, Go, etc.) are OpenAPI-generated clients — or call HTTP directly.

Current packages: `@amos.com/amos-js` 0.11.16, `@amos.com/react-amos-js` 0.11.15, and `@amos.com/node` 0.1.58 (peer `>=0.1.57`). `@amos.com/node` is a **peer dependency** of both client SDKs (install it for OpenAPI types even in browser-only TypeScript). Prefer the installed package README + types over inventing APIs.

## Architecture

```
Merchant browser                              Amos
─────────────────                             ────
@amos.com/amos-js  ──── postMessage ────►  js*.amos.com iframe
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
| Embed app (`js*.amos.com`) | Iframe **content** (not a partner dependency) |

Docs: [docs.amos.com](https://docs.amos.com). Prefer `@amos.com/react-amos-js` in React; otherwise `@amos.com/amos-js`.

OpenAPI schema types (`PaymentIntent`, `EmbedToken`, `CreatePaymentIntentInput`, etc.) come from `@amos.com/node` as `components["schemas"]["…"]` — client SDKs no longer re-export those aliases.

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
   → await confirmPayment({ token })    ← use it RIGHT AWAY
   → confirm result { status, intent? } ← unlock UI here

❌ open form → create intent → user types for 20+ min → confirm(stale token)
   → Signature has expired
```

Same rule for setup (`await confirmSetup`) and payment intents. Prefetching an intent “to warm up” Save is an anti-pattern.

## Credentials

| Credential | Where | Notes |
|------------|--------|------|
| **Render token** | Client | Dashboard render template; encodes `env`, origins, methods, amount range, `billing_address_options`, bank `options.verification` |
| **API key** | Server only | Never ship to the browser |
| **Account ID** | Server / approval | Provided after app approval |

**Env coupling (do not mix):**

| | Sandbox | Production |
|--|---------|------------|
| Dashboard | `dashboard-sandbox.amos.com` | `dashboard.amos.com` |
| Pay API | `https://api-sandbox.amos.com` | `https://api.amos.com` |
| Embed | `https://js-sandbox.amos.com` | `https://js.amos.com` |

Parent pages that pin CSP must allow `frame-src https://js.amos.com https://js-sandbox.amos.com` (and `Permissions-Policy payment=` for those origins) **before** picking up an SDK that uses the new hosts. Older SDKs still load `embed.amos.com` / `embed-sandbox.amos.com`. Dashboard allowed origins may be concrete (`https://checkout.example.com`) or CSP-style wildcards (`https://*.example.com`).

`@amos.com/node` exports `AMOS_API_BASE_URL_SANDBOX` / `AMOS_API_BASE_URL_PRODUCTION` and `AMOS_API_VERSION`. Do not use the old `PAY_API_*` names or `pay.amos.com` hosts.

Client SDK picks embed host via `getEmbedOrigin(renderToken)`. Render templates also encode billing geography (`billing_address_options`: `us_only` + `allowed_states`, or `international` + `allowed_countries`). Addresses outside that set are rejected. Bank methods may set `options.verification` (`false` disables Plaid).

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

Call from **submit / express `onConfirm`**. Do not create on page load. Map Pay API errors to safe client messages.

## `confirmPayment` / `confirmSetup` (await — do not fire-and-forget)

Canonical helpers: **`confirmPayment`** (payment intent) and **`confirmSetup`** (setup intent).

They return **`Promise<ConfirmPaymentResult>`** / **`Promise<ConfirmSetupResult>`**. **Await** them so you can stop spinners. Confirm is **synchronous authorization**: the Promise settles after the processor approves or declines, or after a timeout.

```ts
type ConfirmPaymentResult =
  | { status: "succeeded"; paymentIntent: PaymentIntent }
  | { status: "failed"; error: "timeout" }
  | { status: "failed"; paymentIntent?: PaymentIntent };

type ConfirmSetupResult =
  | { status: "succeeded"; setupIntent: SetupIntent }
  | { status: "failed"; error: "timeout" }
  | { status: "failed"; setupIntent?: SetupIntent };
```

| Result | Meaning | Host action |
|--------|---------|-------------|
| `succeeded` | Processor **authorized** (sale completed for `capture_method: "automatic"`). Capture for **`automatic_async` may still finish asynchronously**. | Run success UX; **verify via webhook or server retrieve** (not settlement proof). |
| `failed` (no `error`) | Declined or validation. Recoverable **field errors stay in the iframe**. `paymentIntent` / `setupIntent` present when the confirm API returned a body — inspect **`state`**. | Unlock UI. Do **not** duplicate per-field errors on the host. Customer can fix and retry. Optional generic banner is OK. |
| `failed` + `error: "timeout"` (`isConfirmTimeout(result)`) | Iframe did not post `CONFIRMATION_RESULT` within **15s** (`CONFIRM_TIMEOUT_MS`), or embed aborted hung `/confirm` at **10s**. **Not a decline** — the charge may still settle. | Unlock UI. Do **not** retry as a new payment. Verify via webhook / server retrieve. |

Use **`isConfirmTimeout(result)`** (re-exported from both client SDKs). Do not treat a bare `{ status: "failed" }` as a timeout.

When the confirm API returned a body, the result includes `paymentIntent` or `setupIntent`. Payment intents expose failure `state`; `last_payment_error` is not on the contract. Retrieve server-side or wait for webhooks when the result has no intent.

To clear fields and API errors without remounting (e.g. after success when starting another payment), call **`resetForm`** with the same iframe ref/element. It restores the latest mounted/updated `defaultValues`; on bank it also disconnects Plaid.

**Removed (do not use):** `onResult` / `ConfirmationResult` / `incomplete`, `confirmPaymentIntent` / `confirmSetupIntent`, `onPaymentIntentConfirmationSucceeded`, `onSetupIntentConfirmationSucceeded`, `onConfirmationFailed`.

## `onValidityChange` (card / bank)

Optional. The iframe posts `{ isValid }` when required fields become valid or invalid (**no PCI data**). Use it to enable/disable the host Pay/Save button. Still call `validateForm` on submit — `onValidityChange` is button UX, not a substitute for the submit gate.

## `onCardBrandChanged` (card only)

Optional. The credit-card iframe posts `{ brand }` when the detected network changes (**no PCI data** — no PAN, last4, or BIN). `brand` is `"visa"` | `"mastercard"` | `"amex"` | `"discover"` | `"diners"` | `"jcb"`, or `null` when the field is empty or the digits do not match a known brand. Never fired for bank. Use it for host UX (icons, surcharge copy) — not as a substitute for `validateForm`.

## Enter in the iframe (card / bank — Stripe pattern)

The card/bank iframe is **cross-origin**. The parent **cannot** see Enter while focus is inside it (`keydown` on `window` will not fire). Do **not** invent `onSubmitRequest` or a host key listener.

**Required:** wrap the mount in a host `<form>` and handle **that form’s `submit`**. Enter in the iframe posts PCI-safe `{ type: "FORM_SUBMIT_REQUEST" }` (no field values); the SDK calls `requestSubmit()` on the enclosing form. Same handler as the Pay/Save button (`type="submit"`). Always `preventDefault` in `onSubmit`.

No enclosing `<form>` → no-op. Plaid Embedded Institution Search showing (bank iframe hidden) → no-op. Parent fields (email, amount) still submit on Enter when *they* are focused.

```tsx
<form onSubmit={handleSubmit}>
  <AmosCreditCardPaymentMethodForm ref={iframeRef} renderToken={renderToken} />
  <button type="submit">Pay now</button>
</form>
```

## Escape in the iframe (card / bank — modals)

The iframe is **cross-origin**. Parent `keydown` cannot see Escape while focus is inside it. Pass **`onEscapeKeyPressed`** to close a host modal. PCI-safe (no field values). Not fired while an iframe dropdown or address suggestion list is open (that Escape dismisses the overlay first), or while Plaid Embedded Institution Search is showing. Do **not** invent a parent `keydown` listener for this.

## Appearance (card / bank)

Optional `appearance` on card/bank mounts. **Wallet buttons do not take `appearance`.** Applied after handshake via `UPDATE_APPEARANCE` — never put it on the iframe `src` (that 307s and breaks postMessage). Use the mount helpers / React components; do not invent `appearanceWithDefaults` or `amosReload`.

```ts
appearance?: {
  labels?: "above" | "floating" | "placeholder";
  themeVariables?: Partial<Record<ThemeVariable, string>>;
  fonts?: FontSource[]; // { cssSrc } | { family, src, display?, style?, weight?, unicodeRange? }
  rules?: Partial<Record<AppearanceRuleSelector, AppearanceRuleDeclarations>>;
}
```

**Replace model** (mount / React `update`, same as the iframe):

| Key | When provided | When omitted |
|-----|----------------|--------------|
| `themeVariables` | **Replace** the full override set. Unlisted variables revert to iframe defaults. | Keep previous |
| `fonts` / `rules` / `labels` | **Replace** (`fonts: []` / `rules: {}` clears) | Keep previous |

A `themeVariables` patch that omits `--font-family` still gets Inter filled in by `appearanceWithDefaults` (system stack if that payload also has `fonts: []`). Do not assume other keys like `--primary` or `--radius` are kept — restating `themeVariables` drops them unless you include them.

**Fonts.** `https:` only (embed accepts max 8). `{ cssSrc }` (Google Fonts CSS or self-hosted stylesheet — iframe injects `<link rel="stylesheet">`) or custom `{ family, src }` (`src` is a CSS `src` list of `url("https://…")`). Pair with `--font-family` so the loaded face is used. The iframe does **not** wait for webfonts (`font-display: swap`). Parent CSP does not need `fonts.googleapis.com` (loaded inside the iframe).

Default on first paint when `fonts` and `--font-family` are omitted: SDK sends Google Fonts Inter and `--font-family: Inter, ui-sans-serif, system-ui, sans-serif`. `fonts: []` without `--font-family` → system stack (`ui-sans-serif, system-ui, sans-serif`).

The host skeleton copies `themeVariables` and resting **`.Input` / `.Label`** rules. It does **not** inject webfonts — load the face on the host page if the skeleton should match; otherwise it uses `ui-sans-serif, system-ui, sans-serif`.

**Rules.** Stripe-style class names (`.Input`, `.Label`, `.Error`, …) mapped onto iframe slots — you cannot style the iframe DOM from the host. They override `themeVariables` for the properties they set. Values may be `var(--primary)` (allowlisted theme tokens, no fallback). Unknown selectors/properties are ignored. `--input-height` / `--floating-input-height` are a **minimum**; `.Input` `padding` / `fontSize` / `lineHeight` can grow the field. Selectors and declaration keys: [api-reference.md](api-reference.md).

On bank, `themeVariables` also style the parent-page Plaid panel (unset vars inherit from the host page).

## Non-express flow (card / bank)

```
mount form inside host <form> (render token) [+ onValidityChange]
  → user fills iframe
  → Pay click OR Enter in iframe  →  host submit
  → validateForm
  → your server creates intent   ← embed token minted here
  → await confirmPayment / confirmSetup
  → confirm result
```

| | Payment intent | Setup intent |
|--|----------------|--------------|
| Server | `POST /payment_intents` | `POST /setup_intents` |
| Client confirm | `await confirmPayment({ …, token })` | `await confirmSetup({ …, token })` |

**Loading skeletons (do not invent your own):** card/bank mounts show a field-shaped skeleton (sized from `appearance`, `additionalFields`, `billingAddressRequirement`). Google Pay / Apple Pay mounts show a **button-shaped** skeleton at `height` (default `"48px"`). The SDK replaces the skeleton with the iframe when appearance is ready. Do not overlay a host-page placeholder or hide the mount until “ready.”

### Tabs / multiple methods (keep mounted)

If checkout switches between methods (card, bank, etc.) with tabs or similar UI, **mount every form you offer up front** and hide inactive ones with CSS. Do not mount only the selected tab. Still wrap them in **one host `<form>`** so Enter in the visible iframe submits checkout.

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

1. Wrap `AmosCreditCardPaymentMethodForm` or `AmosBankAccountPaymentMethodForm` in a host `<form onSubmit={…}>`. The component mounts into a wrapper `div`; **`ref` still points at the iframe**.
2. Keep `ref` on the component; pass the **same** `iframeRef` to helpers (not the wrapper).
3. Optional: `onValidityChange={({ isValid }) => …}` to enable/disable the submit button. Card only: `onCardBrandChanged={({ brand }) => …}`. Modal: `onEscapeKeyPressed` to close it.
4. On **form `submit`** (Pay button **or** Enter in the iframe): `preventDefault`, then `await validateForm({ iframeRef })` → if false, stop. Do not attach a parent `keydown` for Enter.
5. Call **your** backend → `{ token }`.
6. Immediately `const result = await confirmPayment({ iframeRef, token })` or `await confirmSetup(...)`.
7. Unlock from the result. On `isConfirmTimeout(result)`, do not retry. On other `failed`, field errors are already in the iframe; on `succeeded`, run success UX then verify server-side.
8. Optional: `resetForm({ iframeRef })` after confirm when clearing the form for another attempt (without destroying the mount).

Optional props: `appearance` (**card/bank only** — fonts, rules, `themeVariables` including `--font-family`; also styles the parent-page **Plaid** panel), `defaultValues`, `onValidityChange`, `onEscapeKeyPressed`, card `onCardBrandChanged`, `billingAddressRequirement?: "country" | "full"` (`country` collects country/region and postal for CA / PR / GB / US; `full` is street address + Smarty autocomplete), card `additionalFields?: { cardholderName: boolean }`. Bank supports **`requireAchVerification?: boolean`** and **`intent?: "payment" | "setup"`** (see Plaid below).

Do **not** create the intent in `useEffect` on mount/open.

### Vanilla

Same with `mountAmosCreditCardPaymentMethodForm` / `mountAmosBankAccountPaymentMethodForm` (skeleton is automatic) **inside a host `<form>`**, then listen to that form’s `submit` (not only a button `click`). `validateForm({ iframe: card.iframe })` and `await confirmPayment({ iframe: card.iframe, token })` (or `confirmSetup`). Pass `defaultValues` / `onValidityChange` / `onEscapeKeyPressed` on mount; card: `onCardBrandChanged`. Bank: pass `requireAchVerification: true` when the payment requires Plaid, and `intent: "setup"` when saving. Use `controller.update({ defaultValues, appearance })`, `controller.focus(field)`, and `resetForm({ iframe: card.iframe })` without remounting.

## Populate and focus card/bank fields

`defaultValues` accepts non-sensitive name and billing address fields only:

```ts
type PaymentMethodFormDefaultValues = {
  name?: string;
  billingAddress?: {
    line1?: string;
    line2?: string;
    city?: string;
    state?: string;
    postalCode?: string;
    country?: string;
  };
};
```

- React: pass `defaultValues` to the card/bank component. Pass it to `confirmPayment` / `confirmSetup` for a one-confirm overlay that does not replace reset defaults.
- Vanilla: pass it on mount or call `controller.update({ defaultValues })`.
- Focus: React `focusField({ iframeRef, field })`; vanilla `controller.focus(field)`. Calls queue until the iframe is ready and no-op for hidden, wrong-form, or Plaid-covered fields.
- Never use defaults for PAN, CVC, routing number, or account number.

### Bank ACH / Plaid (Embedded Institution Search)

When ACH verification is required, the SDK **hides the routing/account iframe** and mounts [Plaid Embedded Institution Search](https://plaid.com/docs/link/embedded-institution-search/) (`Plaid.createEmbedded`) on the **parent** page. After success: linked bank + Disconnect; `onValidityChange({ isValid: true })`. Confirm still uses `validateForm` / `confirmPayment` / `confirmSetup` — the SDK attaches `payment_method.plaid` (`public_token`, `account_id`) and omits `bank_account_profile_attributes`. Do not collect routing/account numbers, mint link tokens, or load Plaid yourself. Hosts do not proxy Pay API (`GET /merchants`, `POST /plaid_link_tokens`); the bank iframe does that.

**`requireAchVerification`** (boolean, default `false`): for payment intents, set this from your own business rule when Plaid is required. Optional helper: `requiresAchVerification({ amount, achThreshold })` (integer cents). The Pay API no longer exposes `Account.ach_threshold` — hosts that still have a threshold compute this themselves.

**`intent`** (`"payment"` | `"setup"`, default `"payment"`): `"setup"` always shows Plaid. Changing `intent` remounts the bank iframe.

| When | Behavior |
|------|----------|
| Render token `verification: false` | Always manual bank form (no Plaid) |
| `intent: "setup"` (verification on) | Always Plaid Embedded Institution Search |
| `intent: "payment"`, `requireAchVerification: true` | Plaid Embedded Institution Search |
| `intent: "payment"`, omitted/false `requireAchVerification` | Manual bank form |

Update `requireAchVerification` when the host rule changes. `resetForm` also disconnects Plaid.

**Render template:** bank `allowed_payment_methods[].options.verification` — omitted/`true` enables Plaid; `false` disables it (dashboard **Disable verification**, e.g. virtual terminal). Encoded in the render token JWT.

**CSP:** parent page must allow `script-src https://cdn.plaid.com` and `frame-src https://cdn.plaid.com https://*.plaid.com`. Do not load `PLAID_SECRET` / `PLAID_CLIENT_ID` in the browser or iframe.

`appearance.themeVariables` styles the Plaid panel the same way as the iframe (unset vars inherit from the host page).

## Express flow (Google Pay / Apple Pay)

```
mount button → user taps → onConfirm → your server creates PI → return confirmPayment(token)
```

- Required: `amount` (**string** major-currency decimal, e.g. `"50.00"` for $50.00), `merchantName`, **`onConfirm`**. The iframe converts that string to cents in `paymentIntentCreateAttributes.amount` (`CreatePaymentIntentInput`) — forward those attributes to `POST /payment_intents` as-is.
- **`onConfirm({ paymentIntentCreateAttributes, customerCreateAttributes, confirmPayment })`**: create the intent on your server, then **`return confirmPayment(token)`** (`Promise<ConfirmPaymentResult>`). The SDK does **not** auto-confirm.
- Do **not** call `validateForm` or `confirmPayment({ iframe })` yourself from the host — use the `confirmPayment` function injected into `onConfirm`.
- Map iframe create attributes onto Pay API bodies (`payment_intent`, `customer`) on the server.
- Components: `AmosGooglePayButton` / `AmosApplePayButton` (React) or `mountAmosGooglePayButton` / `mountAmosApplePayButton` (vanilla).
- Wallet buttons do **not** take `appearance`. They show a **button-shaped skeleton** at `height` until the iframe is ready — do not overlay a host placeholder.
- **Layout:** the branded button fills the iframe. `height` is a CSS length (default `"48px"`). Size the **mount slot** (container width), not the button. Compact Google Pay: `buttonProps: { buttonSizeMode: "static", style: { width: "240px" } }`.
- **`buttonProps`:** native button options. Google Pay omitted fields keep `buttonType: "plain"` and `buttonSizeMode: "fill"` (`buttonColor`, `buttonBorderType`, `buttonLocale`, `style`, …). Apple Pay omitted fields keep `buttonstyle: "black"`, `type: "plain"`, `locale: "en-US"` (`style.width` also sets `--apple-pay-button-width` unless you set that custom property).
- **Host iframe:** React `iframeProps` (`style`, `className`, `id`). Vanilla `iframeClassName` / `iframeStyle`. Use CSS values with units (`{ borderRadius: "8px" }`).
- **Removed (do not use):** `onInitiatePaymentIntentRequest` (use `onConfirm` and `return confirmPayment(token)`), `onResult`. `fullWidth` and top-level `buttonType` / `buttonstyle` / `type` / `style` / `buttonStyle` belong in `buttonProps` (and `height` for painted height). Wallet card profiles send only `wallet_payload` — do not invent `wallet_provider` / PAN / cryptogram fields.
- Apple Pay: Safari uses the native sheet; other browsers use Apple's QR popup (`pay.apple.com`). SDK shows a host-page waiting overlay with **Cancel payment** while the popup is open. After authorize, Cancel is removed and the overlay shows **Completing your payment…** until `onConfirm` settles — do not reinvent expand/collapse iframe hacks or stack other fixed UI above the overlay.

## PCI rules (non-negotiable)

- Never collect PAN, CVV, or full bank account numbers in merchant DOM.
- Never put API keys or raw payment method confirm payloads on the client.
- Merchant orchestrates tokens; Amos iframes + embed confirm endpoints handle sensitive data. Bank ACH verification uses Plaid Embedded Institution Search on the **parent** page (SDK-owned) — still do not collect account numbers or Plaid client secrets yourself.
- `{ status: "succeeded" }` on a confirm result is **authorization UX**. Use **webhooks** (or server retrieve) before fulfilling or treating a PM as saved.

## Dashboard prerequisites (blank iframe checklist)

1. Add **parent origin(s)** (exact scheme + host, or CSP-style `https://*.example.com`).
2. Create a **render template** with allowed methods (and billing geography). Bank templates can **Disable verification** (`options.verification: false`) to skip Plaid.
3. Issue a **render token**.
4. Use an **API key** from the same environment.

Mismatch → blank iframe or method not allowed.

## Common pitfalls

| Symptom / mistake | Fix |
|-------------------|-----|
| Blank iframe | Origin/method not on render template; env mismatch |
| Billing address rejected | Render template `billing_address_options` (`us_only` / `international`) |
| `validateForm` always false | Iframe not ready; 5s timeout; wrong iframe ref; bank Plaid mode and customer has not linked yet |
| Confirm no-ops / always `failed` | Pass mounted `iframe` / `iframeRef`, not the container / React wrapper `div`; **await** the Promise |
| Custom card/bank/wallet loading UI | SDK already shows a field skeleton (card/bank) or button skeleton (GPay/Apple Pay); don’t overlay or hide the mount |
| Tab switch remounts / flashes skeleton | Keep all method forms mounted; hide inactive tabs with CSS (`hidden`) |
| Wrong confirm helper | Payment → `confirmPayment`; setup → `confirmSetup` |
| `onResult` / `ConfirmationResult` / `incomplete` | Removed. Await `confirmPayment` / `confirmSetup`; branch on `status` and use the optional returned intent |
| `confirmPaymentIntent` / `confirmSetupIntent` | Removed. Use `confirmPayment` / `confirmSetup` |
| Spinner never stops | Await confirm; `succeeded`, decline `failed`, and timeout all unlock UI |
| Confirm `failed` after ~15s / retrying a timeout | Use `isConfirmTimeout(result)`. Timeout is uncertain, not a decline — do not create a new intent and confirm again. Verify webhook / retrieve. |
| Need to clear form after success/retry | `resetForm({ iframeRef })` / `resetForm({ iframe })` — also disconnects Plaid; do not remount unless needed |
| Need to populate name/address | Pass `defaultValues`; never pass sensitive account/card fields |
| Need to focus an iframe field | React `focusField({ iframeRef, field })`; vanilla `controller.focus(field)` |
| Pay/Save button never enables | Wire `onValidityChange({ isValid })`; still `validateForm` on submit |
| Enter in iframe does nothing | Wrap the mount in a host `<form>` and handle `submit` (`preventDefault`). Parent `keydown` cannot see keys in the cross-origin iframe. |
| Inventing `onSubmitRequest` / host Enter listener | Do not add a callback or parent `keydown`. SDK submits the enclosing form (`FORM_SUBMIT_REQUEST`). Pay button `type="submit"`. Guard `processing` so Enter cannot double-submit. |
| Escape in iframe does not close the modal | Pass `onEscapeKeyPressed`. Parent `keydown` cannot see Escape in the iframe. Not fired while a dropdown / address list is open, or while Plaid is showing. |
| Custom font not applied | Pair `appearance.fonts` with `--font-family`. `https:` only. `fonts: []` skips the webfont. |
| Theme patch dropped `--primary` / `--radius` | `themeVariables` is **replace**, not merge. Restate every override you still want. Omitted `--font-family` is filled with Inter (or the system stack when `fonts: []`). |
| Styling iframe fields from the host page | Use `appearance.rules` (Stripe-style `.Input` / `.Label` / …). You cannot target the iframe DOM. Unknown selectors/properties are ignored. |
| Putting `appearance` on the iframe URL | Appearance is postMessage after handshake. Canonical src params are `token`, `additionalFields`, `billingAddressRequirement`, `intent` only. |
| Using `onCardBrandChanged` as BIN/PAN | Event is `{ brand }` only (or `null`); card form only — not bank |
| **`Signature has expired`** | Create intent on submit/tap; confirm immediately |
| Creating intent on mount/open | Move create into submit / `onConfirm` after `validateForm` |
| GPay/Apple Pay `amount` types | Client prop: major-currency string `"50.00"`; Pay API / `paymentIntentCreateAttributes.amount`: number `5000` (cents). Passing `"5000"` to a wallet button charges $5,000. |
| Setup bank still shows routing/account | Pass `intent: "setup"` |
| Plaid never appears (payment) | Pass `requireAchVerification: true`; ensure render-token `verification` is not false |
| Inventing a Connect button / calling Plaid yourself | Use the bank mount; SDK shows Plaid Embedded Institution Search |
| CSP blocks Plaid | Allow `cdn.plaid.com` + `*.plaid.com` on the **parent** page |
| `onInitiatePaymentIntentRequest` / returning only a token | Breaking: `onConfirm` must `return confirmPayment(token)` |
| `fullWidth` / top-level `buttonType` / `buttonStyle` | Breaking: use `height` + `buttonProps` + React `iframeProps` (vanilla `iframeStyle`) |
| Inventing wallet PAN / `wallet_provider` | Embed confirm sends `card_profile_attributes.wallet_payload` only |
| Importing `PaymentIntent` from amos-js | Use `components` from `@amos.com/node` |
| Mixing sandbox key + prod token | Align dashboard, render token, API key, base URL |
| `PAY_API_*` / `pay.amos.com` | Current `@amos.com/node`: `AMOS_API_*` + `api.amos.com` / `api-sandbox.amos.com` |
| Reading `last_payment_error` | Not on `PaymentIntent`; use returned intent `state`, retrieve, or webhooks |
| Treating confirm `succeeded` as captured | `automatic_async` capture may still be in flight; verify webhook / retrieve |

## Agent workflow

1. Confirm browser stack, **payment vs setup**, methods (including Apple Pay if needed), and **server language / SDK**.
2. Configure Pay API client or raw HTTP; scaffold a route that returns **only** `token`.
3. Scaffold client checkout as a host **`<form onSubmit>`** wrapping the card/bank mount so **Enter in the iframe** submits it (Stripe pattern — no parent `keydown`, no `onSubmitRequest`). Use **`await confirmPayment` / `await confirmSetup`**. Wallets: **`onConfirm`** that creates the intent then **`return confirmPayment(token)`**. Reject create-on-open designs. On card/bank, wire **`onValidityChange`** to the host button; use `defaultValues` / `focusField` for host-driven form UX. On card, optional **`onCardBrandChanged`**. In a modal, pass **`onEscapeKeyPressed`**. Style with **`appearance.fonts`**, **`--font-family`**, **`themeVariables`**, and **`rules`** — do not target the iframe DOM. On bank, set **`requireAchVerification`** from the host rule and **`intent: "setup"`** when saving. Allow Plaid CSP unless the render token disables verification. If the UI uses method tabs, mount every form and hide inactive ones with CSS.
4. Handle `succeeded` / `failed` / **`isConfirmTimeout`**; inspect the returned intent `state` when present, and remind about dashboard origins and webhooks (`payment_intent.succeeded` / `setup_intent.succeeded`).
5. Read installed package versions if APIs look unfamiliar. Current clients use `confirmPayment` / `confirmSetup`, `isConfirmTimeout`, wallet **`onConfirm`**, host-form Enter submit, `onEscapeKeyPressed`, `appearance.fonts` / `rules` / `--font-family` (**replace** `themeVariables`), `defaultValues`, `focusField`, `onValidityChange`, card `onCardBrandChanged`, `resetForm`, bank `requireAchVerification` + `intent` (Plaid Embedded Institution Search), and wallet `height` / `buttonProps` / `iframeProps`. Peer `@amos.com/node` `>=0.1.57`.

## Additional resources

- Pay API contract + SDK discovery: [api-reference.md](api-reference.md)
- HTTP, Node, and client snippets: [examples.md](examples.md)
