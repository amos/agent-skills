# Amos Pay API reference

Companion to [SKILL.md](SKILL.md).

**Source of truth:** the Amos Pay OpenAPI contract ([docs.amos.com](https://docs.amos.com)). Backend SDKs are codegen over that spec. Prefer generated types from the SDK in use; otherwise use the HTTP shapes below.

## Environments

| | Sandbox | Production |
|--|---------|------------|
| Dashboard | `https://dashboard-sandbox.amos.com` | `https://dashboard.amos.com` |
| Pay API base URL | `https://api-sandbox.amos.com` | `https://api.amos.com` |
| Embed | `https://embed-sandbox.amos.com` | `https://embed.amos.com` |
| `X-Api-Version` | `1` (until the API bumps; SDK major often tracks this) | same |

`@amos.com/node` (`>=0.1.53`, current 0.1.57): `AMOS_API_BASE_URL_SANDBOX`, `AMOS_API_BASE_URL_PRODUCTION`, `AMOS_API_VERSION`. Requires **Node 22+**. Old names `PAY_API_*` and hosts `pay.amos.com` / `pay-sandbox.amos.com` are gone from the SDK. OpenAPI `servers` may still list `pay-sandbox.amos.com` — use the Node constants.

## Auth (merchant server → Pay API)

```http
X-Api-Key: <secret>
X-Api-Version: 1
X-Idempotency-Key: <uuid>    # when OpenAPI documents it (refunds, payouts, voids)
Content-Type: application/json
```

Never expose `X-Api-Key` to browsers. Auth is resolved from the API key — do not send a separate `X-Account-Id` header (removed from the contract).

## Operations for iframe payment-method flows

| Operation | Method + path | Request body schema | Success body |
|-----------|---------------|---------------------|--------------|
| Create payment intent | `POST /payment_intents` | `CreatePaymentIntentRequest` | `EmbedToken` |
| Create setup intent | `POST /setup_intents` | `CreateSetupIntentRequest` | `EmbedToken` |
| Create customer (optional) | `POST /customers` | `CreateCustomerRequest` | `Customer` |
| Get payment intent (optional) | `GET /payment_intents/{id}` | — | `PaymentIntent` |
| Get setup intent (optional) | `GET /setup_intents/{id}` | — | `SetupIntent` |

Search the installed SDK / OpenAPI artifact for these **paths** when method names differ by language.

### Create payment intent (charge now)

```http
POST {baseUrl}/payment_intents
```

```json
{
  "payment_intent": {
    "amount": 5000,
    "capture_method": "automatic",
    "customer_id": "<uuid optional>",
    "description": null,
    "statement_descriptor": "optional",
    "metadata": {}
  }
}
```

- Nested body is `CreatePaymentIntentInput`. `amount` is **integer cents** (JSON number). No per-intent `currency` (account-level).
- `capture_method`: `"automatic"` (sale) | `"automatic_async"` (auth then async capture) | `"manual"` (auth only; capture separately). Client `confirmPayment` `succeeded` means **authorization** (or sale for `automatic`); `automatic_async` capture may still be in flight.
- Optional `recurring_payment` for MIT/recurring (see OpenAPI `RecurringPayment`).
- **200** → `EmbedToken`:

```json
{ "token": "<jwt>", "ttl": 3600 }
```

Return `token` to the browser for `confirmPayment`.

### Create setup intent (save payment method, no charge)

```http
POST {baseUrl}/setup_intents
```

```json
{
  "setup_intent": {
    "customer_id": "<uuid optional>",
    "metadata": {}
  }
}
```

**200** → `EmbedToken` (same shape). Browser uses `confirmSetup`.

### Create customer

```http
POST {baseUrl}/customers
```

```json
{
  "customer": {
    "email": "alex@example.com",
    "name": "optional",
    "phone": "optional",
    "metadata": {}
  }
}
```

**201** → `Customer` (includes `id`). Pass `id` as `customer_id` on the intent when associating. Optional `mailing_address_attributes` (`MailingAddressInput`: line1/2, city, country, postal_code, state, name). Wallet `onConfirm` receives the nested `CreateCustomerInput` / `CreatePaymentIntentInput` — wrap them as `{ customer }` / `{ payment_intent }` on the Pay API.

### Retrieve after confirm

`PaymentIntent.last_payment_error` and `Account.ach_threshold` have been removed from the API contract. Use payment-intent `state`, server retrieve, and webhooks for outcomes. Decide payment-time ACH verification in the host and pass `requireAchVerification`.

## Working with any generated SDK

1. **Install / import** the official Amos client for the server language.
2. **Construct** with `baseUrl` = sandbox or production Pay API host.
3. **Inject** `X-Api-Key`, `X-Api-Version`.
4. **Resolve the operation:**
   - Path-style (openapi-fetch): `client.POST("/payment_intents", { body })`
   - RPC-style: `createPaymentIntent` / `payment_intents.create` — verify against path in generated docs
5. **Pass the nested body** (`payment_intent: { … }` / `setup_intent: { … }`) unless the SDK flattens it.
6. **Extract `response.token`**. That string is what iframe client SDKs need.
7. **Handle non-2xx** with the SDK’s error type; map to a safe browser message.

### TypeScript (`@amos.com/node`)

```ts
import {
  createPayApiClient,
  AMOS_API_BASE_URL_SANDBOX,
  AMOS_API_VERSION,
} from "@amos.com/node";

const pay = createPayApiClient({
  baseUrl: AMOS_API_BASE_URL_SANDBOX,
  headers: {
    "X-Api-Key": process.env.AMOS_API_KEY!,
    "X-Api-Version": AMOS_API_VERSION,
  },
});

const pi = await pay.POST("/payment_intents", {
  body: {
    payment_intent: { amount: 5000, capture_method: "automatic" },
  },
});
// pi.data: EmbedToken → pi.data.token

const si = await pay.POST("/setup_intents", {
  body: { setup_intent: { customer_id: optionalCustomerId } },
});
// si.data.token
```

## Embed confirm (Amos iframe only)

Partners do **not** call these for standard iframe flows. The embed app does.

**Prefer synchronous** (blocks until processor auth/sale or card verification):

- `POST /embed/payment_intents/{id}/confirm` → **200** `PaymentIntent` (or **202** if confirmation already started)
- `POST /embed/setup_intents/{id}/confirm` → **200** `SetupIntent` (bank setups succeed without processor auth)

**Legacy async** (migration only; **202** `processing_*` / `verifying`):

- `POST /embed/payment_intents/{id}/confirm_with_payment_method`
- `POST /embed/setup_intents/{id}/confirm_with_payment_method`

Auth: `Authorization: Embed <embedToken>`. Payment method material stays in Amos infrastructure. Bank confirm: send `plaid` and omit `bank_account_profile_attributes` when verification is required; otherwise send encrypted account + routing. Wallet confirm: `card_profile_attributes.wallet_payload` only (no client `wallet_provider` / PAN / cryptogram).

## Client iframe SDKs

### URLs (built by SDK)

| Method | Path |
|--------|------|
| Card | `{embedOrigin}/iframe/card?token={renderToken}&additionalFields=…` |
| Bank | `{embedOrigin}/iframe/bank?token={renderToken}` (`intent=setup` when saving) |
| Google Pay | `{embedOrigin}/iframe/google-pay?token={renderToken}` (`allow="payment"`) |
| Apple Pay | `{embedOrigin}/iframe/apple-pay?token={renderToken}` (`allow="payment"`) |

### `@amos.com/amos-js`

| Helper | Use |
|--------|-----|
| `mountAmosCreditCardPaymentMethodForm` | Card |
| `mountAmosBankAccountPaymentMethodForm` | Bank |
| `mountAmosGooglePayButton` | GPay |
| `mountAmosApplePayButton` | Apple Pay |
| `validateForm({ iframe })` | `Promise<boolean>` (5s timeout → `false`; Plaid mode resolves immediately from Connect state) |
| `confirmPayment` / `confirmSetup` | Non-express confirm — `Promise<ConfirmPaymentResult>` / `Promise<ConfirmSetupResult>` (60s timeout → `failed`) |
| `resetForm({ iframe })` | Clear fields/errors, restore mounted/updated defaults, and disconnect Plaid |
| `updateDefaultValues` / `focusField` | Populate safe name/address defaults or focus a named field |
| `controller.update` / `focus` / `destroy` | Patch options, focus a field, or tear down |
| `getEmbedOrigin` / `decodeJwt` | Token / env helpers |

Required on every mount: **`renderToken`**.

Wallet mounts require **`onConfirm({ paymentIntentCreateAttributes, customerCreateAttributes, confirmPayment }) => Promise<ConfirmPaymentResult>`**. Create the intent, then `return confirmPayment(token)`. Do not use `onInitiatePaymentIntentRequest`.

Optional on card/bank: **`onValidityChange({ isValid })`** — PCI-safe; enable/disable the host button. Still `validateForm` on submit. On bank, `isValid` is also true after Plaid Link returns credentials.

Optional on **card only**: **`onCardBrandChanged({ brand })`** — PCI-safe (`CardBrand | null`). `brand` is `"visa"` | `"mastercard"` | `"amex"` | `"discover"` | `"diners"` | `"jcb"`, or `null` when empty / unknown. Does not include PAN, last4, or BIN. Never fired for bank.

Bank form **`requireAchVerification?: boolean`** (default `false`) and **`intent?: "payment" | "setup"`** (default `"payment"`). For payments, `true` shows Connect / Plaid; for setup, Plaid is always used. Render-token `verification: false` disables verification in either case. When verification is required, the SDK hides the routing/account iframe and renders a parent-page **Connect bank account** button, then opens Plaid Link. Confirm still uses `validateForm` / `confirmPayment` / `confirmSetup` — the SDK attaches `plaid: { public_token, account_id }` (`PlaidCredentialsInput`) and omits `bank_account_profile_attributes`. **CSP:** `script-src https://cdn.plaid.com` and `frame-src https://cdn.plaid.com https://*.plaid.com`. Changing `intent` remounts the bank iframe.

Card and bank forms accept **`defaultValues`** for non-sensitive name and billing-address fields. React also exports `focusField({ iframeRef, field })`; vanilla controllers support `update({ defaultValues })` and `focus(field)`. Never populate PAN, CVC, routing number, or account number.

Card/bank **`mount*` helpers** show a host-page field skeleton (`aria-hidden`) until appearance is ready (1.5s fallback), then fade the iframe in. Skeleton layout follows `appearance.labels`, `additionalFields`, and `billingAddressRequirement`. Google Pay / Apple Pay **`mount*` helpers** show a **button-shaped** skeleton at `height` (default `"48px"`) until appearance is ready. `destroy()` removes the skeleton wrapper. Lower-level `attachPaymentMethodFormListeners` / `attach*PayButtonListeners` do **not** include the skeleton — only the mount helpers (and React components, which call them) do.

Do not set host `opacity` / `height` on the iframe to “fix” loading — that fights the reveal (`pointer-events: none` until shown).

Method tabs: mount every card/bank (and express) form you offer and hide inactive panels with CSS (`hidden`). Do not conditionally unmount on tab change — that reloads the iframe and re-shows the skeleton.

### `@amos.com/react-amos-js`

| API | Use |
|-----|-----|
| `AmosCreditCardPaymentMethodForm` | Card (`ref` → iframe) |
| `AmosBankAccountPaymentMethodForm` | Bank |
| `AmosGooglePayButton` | GPay (`onConfirm`) |
| `AmosApplePayButton` | Apple Pay (`onConfirm`) |
| `validateForm({ iframeRef })` | React ref variant |
| `confirmPayment` / `confirmSetup` | React ref variants returning the intent-aware result types |
| `resetForm({ iframeRef })` | Clear fields/errors, restore defaults, and disconnect Plaid |
| `focusField({ iframeRef, field })` | Focus a named card/bank field |

No Provider. `@amos.com/node` is a **peer dependency** `>=0.1.53` (install for OpenAPI types). Re-exports amos-js helpers/types including `resetForm`, `focusField`, `ConfirmPaymentResult`, `ConfirmSetupResult`, `PaymentMethodFormDefaultValues`, and `PaymentMethodFormField`. Schema types: `components` from `@amos.com/node`. `AmosBankAccountPaymentMethodForm` accepts **`requireAchVerification`** and **`intent`**. Card/bank forms accept `defaultValues`; card accepts `onCardBrandChanged`.

All messaging helpers (`validateForm`, `confirmPayment`, `confirmSetup`, `resetForm`) accept the mounted iframe — React: same `iframeRef` as the form `ref`; vanilla: `controller.iframe`. React card/bank components render a wrapper `div` and mount into it; `ref` / `style` / `className` still target the **iframe**. Wallet buttons take **`iframeProps`** for host-iframe chrome (not top-level `style`).

### Confirm results

```ts
type ConfirmPaymentResult =
  | { status: "succeeded"; paymentIntent: PaymentIntent }
  | { status: "failed"; paymentIntent?: PaymentIntent };

type ConfirmSetupResult =
  | { status: "succeeded"; setupIntent: SetupIntent }
  | { status: "failed"; setupIntent?: SetupIntent };
```

Await `confirmPayment` / `confirmSetup`. On `failed`, field errors are shown under iframe fields and the returned intent is optional. On `succeeded`, drive success UX from the required returned intent, then verify via webhook / server retrieve. There is no `errorMessage` or `incomplete`.

### Express button chrome (optional)

Wallet buttons do **not** take `appearance`. The branded button fills the iframe; size the **mount slot**.

| Prop | Where | Notes |
|------|--------|------|
| `height` | Top-level | CSS length, default `"48px"`. Apple ignores CSS `height`; Amos maps it. |
| `buttonProps` | Top-level object | Native GPay `ButtonOptions` / `<apple-pay-button>` attrs + inner `style`. Omitted GPay fields: `plain` / `fill`. Omitted Apple fields: `black` / `plain` / `en-US`. |
| `iframeProps` | React | Host `<iframe>` (`style`, `className`, `id`). CSS lengths need units. |
| `iframeClassName` / `iframeStyle` | Vanilla | Same host-iframe chrome. |
| `onConfirm` | Required | `{ paymentIntentCreateAttributes, customerCreateAttributes, confirmPayment }` → create PI → `return confirmPayment(token)`. |

Compact Google Pay: `buttonProps: { buttonSizeMode: "static", style: { width: "240px" } }`.

**Removed:** `onResult`, `ConfirmationResult`, `confirmPaymentIntent` / `confirmSetupIntent`, `onInitiatePaymentIntentRequest`, `fullWidth`, top-level `buttonType` / `buttonstyle` / `type` / `style` / `buttonStyle`.

Wallet iframes are flush (`width: 100%`, `margin: 0`); card/bank iframes still use the 8px bleed. A button-shaped skeleton is shown immediately at `height` and replaced when appearance is ready.

## Appearance

```ts
appearance?: {
  labels?: "above" | "floating" | "placeholder";
  themeVariables?: Partial<Record<ThemeVariable, string>>;
}
```

`themeVariables` is **replace**, not merge. **Card/bank only** — wallet buttons do not take `appearance`. On bank, the same variables style the parent-page **Connect bank account** button (unset vars inherit from the host page). Full `ThemeVariable` list is in the installed SDK README.

Card/bank also accept `billingAddressRequirement?: "country" | "full"` (default `"country"`): `country` collects country/region and, for CA / PR / GB / US, a postal code; `full` is street address with Smarty autocomplete. Render templates restrict geography via `billing_address_options` (`mode: "us_only"` + `allowed_states`, or `mode: "international"` + `allowed_countries`).

## Amount typing

| Surface | Type | Example ($50.00) |
|---------|------|---------|
| Pay API `payment_intent.amount` (card/bank create) | number, integer cents | `5000` |
| Google Pay / Apple Pay `amount` prop (wallet sheet) | string, major-currency decimal | `"50.00"` |
| Wallet `paymentIntentCreateAttributes.amount` | number, integer cents (iframe converts the button prop) | `5000` |

Do not pass `"5000"` as the wallet button amount — it is major units, so that would be $5,000.00.

## Webhooks

Configure in the dashboard. Treat confirm results as UX; act on webhook delivery or server-side retrieve. Relevant events include `payment_intent.succeeded` and `setup_intent.succeeded` (plus cancelled / errored / requires_* variants).

Bank ACH: when the render token enables verification and either `intent` is `"setup"` or payment `requireAchVerification` is true, the **client SDK** shows Connect / Plaid Link on the parent page. `verification: false` on the render template skips Plaid entirely. Confirm still goes through the bank iframe so Amos can attach `plaid` to the payment method. Do not collect Plaid credentials, routing numbers, or account numbers in merchant DOM.

## Internal map (Amos eng)

| Concern | Location |
|---------|----------|
| Browser iframe SDKs | `~/Code/amos-js`, `~/Code/react-amos-js` |
| TS Pay API client + OpenAPI | `~/Code/amos-node` |
| Embed iframe app | `~/Code/amos-ui/apps/embed` |
| Shared payment-method UI package | `~/Code/amos-ui/packages/checkout` |
