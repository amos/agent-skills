# Amos Pay API reference

Companion to [SKILL.md](SKILL.md).

**Source of truth:** the Amos Pay OpenAPI contract ([docs.amos.com](https://docs.amos.com)). Backend SDKs are codegen over that spec. Prefer generated types from the SDK in use; otherwise use the HTTP shapes below.

## Environments

| | Sandbox | Production |
|--|---------|------------|
| Dashboard | `https://dashboard-sandbox.amos.com` | `https://dashboard.amos.com` |
| Pay API base URL | `https://api-sandbox.amos.com` | `https://api.amos.com` |
| Embed | `https://js-sandbox.amos.com` | `https://js.amos.com` |
| `X-Api-Version` | `1` (until the API bumps; SDK major often tracks this) | same |

Parent CSP: `frame-src https://js.amos.com https://js-sandbox.amos.com` (plus `Permissions-Policy payment=` for those origins). Older SDKs still use `embed.amos.com` / `embed-sandbox.amos.com`. Dashboard allowed origins may be concrete or CSP-style `https://*.example.com`.

`@amos.com/node` (`>=0.1.65`, current 0.1.69): `AMOS_API_BASE_URL_SANDBOX`, `AMOS_API_BASE_URL_PRODUCTION`, `AMOS_API_VERSION`. Requires **Node 22+**. Old names `PAY_API_*` and hosts `pay.amos.com` / `pay-sandbox.amos.com` are gone from the SDK. OpenAPI `servers` may still list `pay-sandbox.amos.com` — use the Node constants.

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

Setup intents are **organization-scoped**. `X-Account-Id` is ignored if sent; the customer must belong to the authenticated organization. The embed JWT payload includes `organization_id` and `setup_intent_id` (`account_id` is null). Payment-intent tokens remain account-scoped.

**200** → `EmbedToken` (same shape). Browser uses `confirmSetup` (SDK reads `setup_intent_id` from the JWT).

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

**201** → `Customer` (includes `id`). Pass `id` as `customer_id` on the intent when associating. Optional `mailing_address_attributes` (`MailingAddressInput`: line1/2, city, country, postal_code, state, name). Wallet `onConfirm` receives `WalletCustomerCreateAttributes` (not `CreateCustomerInput`) plus `CreatePaymentIntentInput`. Forward the payment-intent attributes as `{ payment_intent }`. Map nested `billingAddress` (`address_line1`, `state`, `postal_code`) on the server — do not wrap the wallet snapshot as `{ customer }` unchanged.

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

Auth: `Authorization: Embed <embedToken>`. Payment method material stays in Amos infrastructure. Bank confirm: send `plaid` and omit `bank_account_profile_attributes` when verification is required (routing and account numbers are filled server-side from Plaid Auth); otherwise send `routing_number` and `account_number` on `bank_account_profile_attributes`. Wallet confirm: `card_profile_attributes.wallet_payload` only (no client `wallet_provider` / PAN / cryptogram).

## Client iframe SDKs

### URLs (built by SDK)

Canonical search params so the embed router does not 307. Appearance is **not** in the URL — it is applied after handshake via `UPDATE_APPEARANCE`. If `IFRAME_READY` never arrives, the SDK rewrites `src` once with `amosReload` (automatic; do not invent this).

| Method | Path |
|--------|------|
| Card | `{embedOrigin}/iframe/card?token={renderToken}&additionalFields=…&billingAddressRequirement=…&intent=…` |
| Bank | `{embedOrigin}/iframe/bank?token={renderToken}&additionalFields=&billingAddressRequirement=…&intent=…` (`intent=setup` when saving) |
| Google Pay | `{embedOrigin}/iframe/google-pay?token={renderToken}&…` (`allow="payment"`) |
| Apple Pay | `{embedOrigin}/iframe/apple-pay?token={renderToken}&…` (`allow="payment"`) |

### `@amos.com/amos-js`

| Helper | Use |
|--------|-----|
| `mountAmosCreditCardPaymentMethodForm` | Card |
| `mountAmosBankAccountPaymentMethodForm` | Bank |
| `mountAmosGooglePayButton` | GPay |
| `mountAmosApplePayButton` | Apple Pay |
| `validateForm({ iframe })` | `Promise<boolean>` (5s timeout → `false`; Plaid mode resolves immediately from linked state) |
| `confirmPayment` / `confirmSetup` | Non-express confirm — `Promise<ConfirmPaymentResult>` / `Promise<ConfirmSetupResult>` (15s → `{ status: "failed", error: "timeout" }`; use `isConfirmTimeout`) |
| `resetForm({ iframe })` | Clear fields/errors, restore mounted/updated defaults, and disconnect Plaid |
| `updateDefaultValues` / `focusField` | Populate safe name/address defaults or focus a named field |
| `controller.update` / `focus` / `destroy` | Patch options, focus a field, or tear down |
| `getEmbedOrigin` / `decodeJwt` | Token / env helpers |

Required on every mount: **`renderToken`**.

Wallet mounts require **`onConfirm({ paymentIntentCreateAttributes, customerCreateAttributes, confirmPayment }) => Promise<ConfirmPaymentResult>`**. `customerCreateAttributes` is **`WalletCustomerCreateAttributes`**, not `CreateCustomerInput`. Create the intent, then `return confirmPayment(token)`. Optional top-level **`phoneRequired`** / **`shippingAddressRequired`** (default `false`, not `buttonProps`). Do not use `onInitiatePaymentIntentRequest`.

Optional on card/bank: **`onValidityChange({ isValid })`** — PCI-safe; enable/disable the host button. Still `validateForm` on submit. On bank, `isValid` is also true after Plaid Embedded Institution Search returns credentials.

Optional on card/bank: **`onEscapeKeyPressed()`** — PCI-safe; close a host modal. Not fired while an iframe dropdown or address suggestion list is open, or while Plaid is showing. Do not attach a parent `keydown` for Escape.

Enter in a card/bank iframe field submits the **enclosing host `<form>`** (`requestSubmit()`), same as Stripe Elements. Payload is PCI-safe `{ type: "FORM_SUBMIT_REQUEST" }` (no field values). No-op without a host form, or while Plaid Embedded Institution Search is showing. Do not attach a parent `keydown` listener or invent `onSubmitRequest`.

Optional on **card only**: **`onCardBrandChanged({ brand })`** — PCI-safe (`CardBrand | null`). `brand` is `"visa"` | `"mastercard"` | `"amex"` | `"discover"` | `"diners"` | `"jcb"`, or `null` when empty / unknown. Does not include PAN, last4, or BIN. Never fired for bank.

Optional on **card and bank**: **`onPostalCodeChange({ postalCode, country })`** (`PaymentMethodFormPostalCodeChangeEvent`). `postalCode` is a finished billing code, or `null` when a finished code becomes incomplete (deleted or country change). Incomplete keystrokes are not posted. US and PR commit at 5 digits (ZIP+4 is the first 5). Canada commits as `A1A 1A1`. The UK commits at a full postcode. Not called for `defaultValues` or `update({ defaultValues })`. Not fired for Apple Pay or Google Pay. Debounce shipping-rate requests on the host.

Bank form **`requireAchVerification?: boolean`** (default `false`) and **`intent?: "payment" | "setup"`** (default `"payment"`). For payments, `true` shows Plaid Embedded Institution Search; for setup, Plaid is always used. Render-token `verification: false` disables verification in either case. When verification is required, the SDK hides the routing/account iframe and mounts Plaid Embedded Institution Search (`Plaid.createEmbedded`) on the parent. A **350px pulse skeleton** covers the slot until Plaid’s `onLoad` (1.5s fallback). Hosts do not proxy Pay API; the bank iframe mints link tokens. Confirm still uses `validateForm` / `confirmPayment` / `confirmSetup` — the SDK attaches `plaid: { public_token, account_id }` (`PlaidCredentialsInput`) and omits `bank_account_profile_attributes`. **CSP:** `script-src https://cdn.plaid.com` and `frame-src https://cdn.plaid.com https://*.plaid.com`. Changing `intent` remounts the bank iframe.

Card and bank forms accept **`defaultValues`** for non-sensitive name and billing-address fields. React also exports `focusField({ iframeRef, field })`; vanilla controllers support `update({ defaultValues })` and `focus(field)`. Never populate PAN, CVC, routing number, or account number. Wrap card/bank mounts in a host `<form>` so Enter in the iframe submits checkout.

Card/bank **`mount*` helpers** show a host-page field skeleton (`aria-hidden`) while the iframe stays `opacity: 0` at its default pixel height until appearance is applied, or for 1.5s after mount if appearance never acks. The SDK then sets `opacity: 1` with no height animation on that first paint. Skeleton layout follows `appearance.labels`, `additionalFields`, `billingAddressRequirement`, and resting `.Input` / `.Label` rules (not webfonts). When Plaid Embedded Institution Search is showing, a **350px pulse skeleton** covers that slot until Plaid’s `onLoad` (same 1.5s fallback). Google Pay / Apple Pay **`mount*` helpers** show a **button-shaped** skeleton at `height` (default `"48px"`) on the same reveal clock. `destroy()` removes the skeleton wrapper. Lower-level `attachPaymentMethodFormListeners` / `attach*PayButtonListeners` do **not** include the skeleton — only the mount helpers (and React components, which call them) do. `attachPaymentMethodFormListeners` also submits the enclosing host form on `FORM_SUBMIT_REQUEST` and calls `onEscapeKeyPressed` on `ESCAPE_KEY_PRESSED`.

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

No Provider. `@amos.com/node` is a **peer dependency** `>=0.1.65` (install for OpenAPI types). Re-exports amos-js helpers/types including `resetForm`, `focusField`, `isConfirmTimeout`, `CONFIRM_TIMEOUT_MS`, `ConfirmPaymentResult`, `ConfirmSetupResult`, `WalletCustomerCreateAttributes`, `WalletPostalAddress`, `WalletContactRequirements`, `PaymentMethodFormDefaultValues`, `PaymentMethodFormField`, `PaymentMethodFormPostalCodeChangeEvent`, `FontSource`, `AppearanceRuleSelector`, and `AppearanceRuleDeclarations`. Schema types: `components` from `@amos.com/node`. `AmosBankAccountPaymentMethodForm` accepts **`requireAchVerification`** and **`intent`**. Card/bank forms accept `defaultValues`, `onEscapeKeyPressed`, `onPostalCodeChange`, and `appearance` (`fonts`, `rules`, `--font-family`); card accepts `onCardBrandChanged`. Wrap card/bank components in a host `<form onSubmit>` so Enter in the iframe submits checkout.

All messaging helpers (`validateForm`, `confirmPayment`, `confirmSetup`, `resetForm`) accept the mounted iframe — React: same `iframeRef` as the form `ref`; vanilla: `controller.iframe`. React card/bank components render a wrapper `div` and mount into it; `ref` / `style` / `className` still target the **iframe**. Wallet buttons take **`iframeProps`** for host-iframe chrome (not top-level `style`).

### Confirm results

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

Await `confirmPayment` / `confirmSetup`. On decline `failed`, field errors are shown under iframe fields and the returned intent is optional (use `state`). On `succeeded`, drive success UX from the required returned intent, then verify via webhook / server retrieve. There is no `errorMessage` or `incomplete`.

`{ status: "failed", error: "timeout" }` (`isConfirmTimeout(result)`) is **not** a decline. Embed aborts hung `/confirm` at 10s and posts the same shape; the SDK wait is 15s (`CONFIRM_TIMEOUT_MS`). Do not retry as a new payment.

### Express button chrome (optional)

Wallet buttons do **not** take `appearance`. The branded button fills the iframe; size the **mount slot**.

| Prop | Where | Notes |
|------|--------|------|
| `height` | Top-level | CSS length, default `"48px"`. Apple ignores CSS `height`; Amos maps it. |
| `buttonProps` | Top-level object | Native GPay `ButtonOptions` / `<apple-pay-button>` attrs + inner `style`. Omitted GPay fields: `plain` / `fill`. Omitted Apple fields: `black` / `plain` / `en-US`. |
| `iframeProps` | React | Host `<iframe>` (`style`, `className`, `id`). CSS lengths need units. |
| `iframeClassName` / `iframeStyle` | Vanilla | Same host-iframe chrome. |
| `onConfirm` | Required | `{ paymentIntentCreateAttributes, customerCreateAttributes, confirmPayment }` → create PI → `return confirmPayment(token)`. `customerCreateAttributes` is `WalletCustomerCreateAttributes`. |
| `phoneRequired` | Top-level | Collect phone in the sheet. Default `false`. Not `buttonProps`. |
| `shippingAddressRequired` | Top-level | Collect shipping postal address. Default `false`. Name, email, and billing are always required. |

Compact Google Pay: `buttonProps: { buttonSizeMode: "static", style: { width: "240px" } }`.

**Removed:** `onResult`, `ConfirmationResult`, `confirmPaymentIntent` / `confirmSetupIntent`, `onInitiatePaymentIntentRequest`, `fullWidth`, top-level `buttonType` / `buttonstyle` / `type` / `style` / `buttonStyle`.

Wallet iframes are flush (`width: 100%`, `margin: 0`); card/bank iframes still use the 8px bleed. A button-shaped skeleton is shown immediately at `height`. The iframe stays `opacity: 0` at its default pixel height until appearance is applied, or for 1.5s after mount if appearance never acks.

## Appearance

```ts
appearance?: {
  labels?: "above" | "floating" | "placeholder";
  themeVariables?: Partial<Record<ThemeVariable, string>>;
  fonts?: FontSource[];
  rules?: Partial<Record<AppearanceRuleSelector, AppearanceRuleDeclarations>>;
}

type FontSource =
  | { cssSrc: string } // https: stylesheet with @font-face
  | {
      family: string;
      src: string; // CSS src list of url("https://…")
      display?: string; // default "swap"
      style?: string;
      weight?: string;
      unicodeRange?: string;
    };
```

**Card/bank only** — wallet buttons do not take `appearance`. Applied after handshake via `UPDATE_APPEARANCE` (not the iframe URL). On bank, `themeVariables` also style the parent-page Plaid panel (unset vars inherit from the host page). Full `ThemeVariable` list (including `--font-family`, `--floating-value-padding-top`, and `--floating-value-padding-bottom`) is in the installed SDK README.

**Replace model** (iframe + mount / React `update`): including `themeVariables` / `fonts` / `rules` sets the full override; omit to keep the previous value. `fonts: []` / `rules: {}` clears. Unlisted `themeVariables` revert to iframe defaults. A `themeVariables` payload that omits `--font-family` still gets Inter filled in (`appearanceWithDefaults`); `fonts: []` on that payload uses the system stack instead. Do not call `appearanceWithDefaults` yourself unless wiring `UPDATE_APPEARANCE` by hand (`initial: true` only on the first post after `IFRAME_READY`; `{ initial }` is required).

**Fonts.** `https:` only, max 8. Omitted `fonts` + omitted `--font-family` on first paint → SDK sends Google Fonts Inter and `--font-family: Inter, ui-sans-serif, system-ui, sans-serif`. `fonts: []` without `--font-family` → `ui-sans-serif, system-ui, sans-serif`. Pair custom sources with `--font-family`. Iframe does not wait for webfonts.

The host skeleton copies `themeVariables` and resting **`.Input` / `.Label`** rules. It does not inject webfonts.

**Rules.** Stripe-style class names mapped onto iframe slots — you cannot target the iframe DOM. They override `themeVariables` for the properties they set. `--input-height` / `--floating-input-height` are a minimum; `.Input` `padding` / `fontSize` / `lineHeight` can grow the field. Floated input text padding is `--floating-value-padding-top` and `--floating-value-padding-bottom`. Values may be `var(--token)` for an allowlisted theme variable (no fallback). Unknown selectors/properties are ignored. No `url()`, `@font-face`, `<`, `>`, or `\`.

| Selector | Targets |
| --- | --- |
| `.Input` | Text fields, country select, state trigger |
| `.Input:hover`, `.Input:focus`, `.Input:disabled` | Those controls in the given state |
| `.Input--invalid` | Invalid text fields / selects |
| `.Input::placeholder` | Input placeholders |
| `.Label` | All labels (above, floating, radio option text, group titles) |
| `.Label--floating` | Extra styles on floating labels (overrides `.Label`) |
| `.Error` | Field-level error text |
| `.Dropdown` | State list panel |
| `.DropdownItem` | State list rows |
| `.DropdownItem--highlight` | Highlighted state row |
| `.RadioIcon` | Bank radio circle |
| `.RadioIcon--checked` | Checked radio circle |
| `.RadioIconInner` | Radio filled dot |

Allowed declaration keys (camelCase): `fontFamily`, `fontSize`, `fontWeight`, `fontStyle`, `lineHeight`, `letterSpacing`, `textTransform`, `color`, `backgroundColor`, `border`, `borderColor`, `borderWidth`, `borderStyle`, `borderRadius`, `boxShadow`, `outline`, `padding`, `margin`, `opacity`.

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

Bank ACH: when the render token enables verification and either `intent` is `"setup"` or payment `requireAchVerification` is true, the **client SDK** mounts Plaid Embedded Institution Search on the parent page (350px pulse skeleton until `onLoad`). `verification: false` on the render template skips Plaid entirely. Confirm still goes through the bank iframe so Amos can attach `plaid` to the payment method. Do not collect Plaid credentials, routing numbers, or account numbers in merchant DOM.

## Internal map (Amos eng)

| Concern | Location |
|---------|----------|
| Browser iframe SDKs | `~/Code/amos-js`, `~/Code/react-amos-js` |
| TS Pay API client + OpenAPI | `~/Code/amos-node` |
| Embed iframe app | `~/Code/amos-ui/apps/embed` |
| Shared payment-method UI package | `~/Code/amos-ui/packages/checkout` |
