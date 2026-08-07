# Amos Pay API reference

Companion to [SKILL.md](SKILL.md).

**Source of truth:** the Amos Pay OpenAPI contract ([docs.amos.com](https://docs.amos.com)). Backend SDKs are codegen over that spec. Prefer generated types from the SDK in use; otherwise use the HTTP shapes below.

## Environments

| | Sandbox | Production |
|--|---------|------------|
| Dashboard | `https://dashboard-sandbox.amos.com` | `https://dashboard.amos.com` |
| Pay API base URL | `https://pay-sandbox.amos.com` | `https://pay.amos.com` |
| Embed | `https://embed-sandbox.amos.com` | `https://embed.amos.com` |
| `X-Api-Version` | `1` (until the API bumps; SDK major often tracks this) | same |

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
- `capture_method`: `"automatic"` | `"automatic_async"` | `"manual"`.
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
  PAY_API_BASE_URL_SANDBOX,
  PAY_API_VERSION,
} from "@amos.com/node";

const pay = createPayApiClient({
  baseUrl: PAY_API_BASE_URL_SANDBOX,
  headers: {
    "X-Api-Key": process.env.AMOS_API_KEY!,
    "X-Api-Version": PAY_API_VERSION,
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

No Provider. `@amos.com/node` is a **peer dependency** (install for OpenAPI types). Re-exports amos-js helpers/types including `resetForm`, `ConfirmationResult`, `ConfirmationIncompleteReason`. Schema types: `components` from `@amos.com/node`.

All messaging helpers (`validateForm`, `confirm*`, `resetForm`) accept the mounted iframe — React: same `iframeRef` as the form `ref`; vanilla: `controller.iframe`.

### `ConfirmationResult`

```ts
| { status: "succeeded"; intent: "payment"; paymentIntent: … }
| { status: "succeeded"; intent: "setup"; setupIntent: … }
| { status: "incomplete"; reason: "field_errors" | "validation_failed" }
| { status: "failed"; errorMessage: string }
```

Unlock host UI on any `onResult`. On `incomplete`, field errors are shown under iframe fields — host unlocks only. On `failed`, show `errorMessage` on the host page. On `succeeded`, drive success UX then verify via webhook / server retrieve (not settlement proof).

## Appearance

```ts
appearance?: {
  labels?: "above" | "floating" | "placeholder";
  themeVariables?: Partial<Record<ThemeVariable, string>>;
}
```

`themeVariables` is **replace**, not merge. Card/bank also accept `billingAddressRequirement?: "country" | "full"` (default `"country"`).

## Amount typing

| Surface | Type | Example |
|---------|------|---------|
| Pay API `payment_intent.amount` | number | `5000` |
| Google Pay / Apple Pay `amount` prop | string | `"5000"` |

## Webhooks

Configure in the dashboard. Treat `onResult` as UX; act on webhook delivery or server-side retrieve.

## Internal map (Amos eng)

| Concern | Location |
|---------|----------|
| Browser iframe SDKs | `~/Code/amos-js`, `~/Code/react-amos-js` |
| TS Pay API client + OpenAPI | `~/Code/amos-node` |
| Embed iframe app | `~/Code/amos-ui/apps/embed` |
| Shared payment-method UI package | `~/Code/amos-ui/packages/checkout` |
