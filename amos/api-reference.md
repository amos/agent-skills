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

`@amos.com/node` (`>=0.1.37`): `AMOS_API_BASE_URL_SANDBOX`, `AMOS_API_BASE_URL_PRODUCTION`, `AMOS_API_VERSION`. Old names `PAY_API_*` and hosts `pay.amos.com` / `pay-sandbox.amos.com` are gone from the SDK. OpenAPI `servers` may still list `pay-sandbox.amos.com` — use the Node constants.

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

- `amount` is **integer cents** (JSON number). No per-intent `currency` (account-level).
- `capture_method`: `"automatic"` (sale) | `"automatic_async"` (auth then async capture) | `"manual"` (auth only; capture separately).
- Optional `recurring_payment` for MIT/recurring (see OpenAPI `RecurringPayment`).
- **200** → `EmbedToken`:

```json
{ "token": "<jwt>", "ttl": 3600 }
```

Return `token` to the browser for `confirmPaymentIntent`.

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

**200** → `EmbedToken` (same shape). Browser uses `confirmSetupIntent`.

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

**201** → `Customer` (includes `id`). Pass `id` as `customer_id` on the intent when associating.

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

Partners do **not** call these for standard iframe flows. The embed app does:

- `POST /embed/payment_intents/{id}/confirm_with_payment_method`
- `POST /embed/setup_intents/{id}/confirm_with_payment_method`

Auth: `Authorization: Embed <embedToken>`. Payment method material stays in Amos infrastructure.

## Client iframe SDKs

### URLs (built by SDK)

| Method | Path |
|--------|------|
| Card | `{embedOrigin}/iframe/card?token={renderToken}&additionalFields=…` |
| Bank | `{embedOrigin}/iframe/bank?token={renderToken}` |
| Google Pay | `{embedOrigin}/iframe/google-pay?token={renderToken}` (`allow="payment"`) |
| Apple Pay | `{embedOrigin}/iframe/apple-pay?token={renderToken}` (`allow="payment"`) |

### `@amos.com/amos-js`

| Helper | Use |
|--------|-----|
| `mountAmosCreditCardPaymentMethodForm` | Card |
| `mountAmosBankAccountPaymentMethodForm` | Bank |
| `mountAmosGooglePayButton` | GPay |
| `mountAmosApplePayButton` | Apple Pay |
| `validateForm({ iframe })` | `Promise<boolean>` (5s timeout → `false`) |
| `confirmPaymentIntent` / `confirmSetupIntent` | Non-express confirm |
| `resetForm({ iframe })` | Clear field values + API errors (card/bank); call after `onResult` to retry or start a new payment |
| `controller.update` / `destroy` | Patch / teardown |
| `getEmbedOrigin` / `decodeJwt` | Token / env helpers |

Required on every mount: **`onResult(result: ConfirmationResult)`**.

Optional on card/bank: **`onValidityChange({ isValid })`** — PCI-safe; enable/disable the host button. Still `validateForm` on submit.

### `@amos.com/react-amos-js`

| API | Use |
|-----|-----|
| `AmosCreditCardPaymentMethodForm` | Card (`ref` → iframe) |
| `AmosBankAccountPaymentMethodForm` | Bank |
| `AmosGooglePayButton` | GPay |
| `AmosApplePayButton` | Apple Pay |
| `validateForm({ iframeRef })` | React ref variant |
| `confirmPaymentIntent` / `confirmSetupIntent` | React ref variants |
| `resetForm({ iframeRef })` | Clear field values + API errors (card/bank) |

No Provider. `@amos.com/node` is a **peer dependency** `>=0.1.39` (install for OpenAPI types). Re-exports amos-js helpers/types including `resetForm`, `ConfirmationResult`, `ConfirmationIncompleteReason`, `PaymentMethodFormValidityChangeEvent`. Schema types: `components` from `@amos.com/node`.

All messaging helpers (`validateForm`, `confirm*`, `resetForm`) accept the mounted iframe — React: same `iframeRef` as the form `ref`; vanilla: `controller.iframe`.

### `ConfirmationResult`

```ts
| { status: "succeeded"; intent: "payment"; paymentIntent: … }
| { status: "succeeded"; intent: "setup"; setupIntent: … }
| { status: "incomplete"; reason: "field_errors" | "validation_failed" }
| { status: "failed"; errorMessage: string }
```

Unlock host UI on any `onResult`. On `incomplete`, field errors are shown under iframe fields — host unlocks only. On `failed`, show `errorMessage` on the host page. On `succeeded`, drive success UX then verify via webhook / server retrieve (not settlement proof).

### Express button chrome (optional)

Forwarded **into** the iframe (not the iframe element):

- **Google Pay:** `buttonType`, `buttonColor`, `buttonRadius`, `buttonSizeMode`, `buttonLocale`, `buttonBorderType`, `style` (e.g. `{ height: "48px", width: "100%" }` with `buttonSizeMode: "fill"`).
- **Apple Pay:** `buttonstyle`, `type`, `locale`, `style` using `--apple-pay-button-height` / `--apple-pay-button-width` (Apple does not size via CSS `height`).

## Appearance

```ts
appearance?: {
  labels?: "above" | "floating" | "placeholder";
  themeVariables?: Partial<Record<ThemeVariable, string>>;
}
```

`themeVariables` is **replace**, not merge. Full `ThemeVariable` list (`--primary`, `--radius`, `--input-height`, `--floating-label-*`, etc.) is in the installed `@amos.com/amos-js` / `react-amos-js` README.

Card/bank also accept `billingAddressRequirement?: "country" | "full"` (default `"country"`): `country` collects country/region and, for CA / PR / GB / US, a postal code; `full` is street address with Smarty autocomplete. Render templates restrict geography via `billing_address_options` (`mode: "us_only"` + `allowed_states`, or `mode: "international"` + `allowed_countries`).

## Amount typing

| Surface | Type | Example |
|---------|------|---------|
| Pay API `payment_intent.amount` | number | `5000` |
| Google Pay / Apple Pay `amount` prop | string | `"5000"` |

## Webhooks

Configure in the dashboard. Treat `onResult` as UX; act on webhook delivery or server-side retrieve. Relevant events include `payment_intent.succeeded` and `setup_intent.succeeded` (plus cancelled / errored / requires_* variants).

Bank ACH: `PaymentIntent` may include `requires_ach_verification` and `ach_verification` (`plaid_auth` + `link_token`) when the amount is above the ACH verification threshold. That flow belongs to Amos embed confirm — do not collect Plaid credentials or account numbers in merchant DOM.

## Internal map (Amos eng)

| Concern | Location |
|---------|----------|
| Browser iframe SDKs | `~/Code/amos-js`, `~/Code/react-amos-js` |
| TS Pay API client + OpenAPI | `~/Code/amos-node` |
| Embed iframe app | `~/Code/amos-ui/apps/embed` |
| Shared payment-method UI package | `~/Code/amos-ui/packages/checkout` |
