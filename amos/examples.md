# Amos examples

Companion to [SKILL.md](SKILL.md). Server examples show the **HTTP contract** first, then an OpenAPI SDK mapping. Client examples talk only to **your** backend and the iframe SDKs.

## Server: raw HTTP (any language)

### Payment intent

`amount` is integer cents (`5000` = $50.00).

```http
POST https://api-sandbox.amos.com/payment_intents
X-Api-Key: $AMOS_API_KEY
X-Api-Version: 1
Content-Type: application/json

{
  "payment_intent": {
    "amount": 5000,
    "capture_method": "automatic"
  }
}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "ttl": 3600
}
```

Merchant route → browser: `{ "token": "<that token>" }` only.

### Setup intent (save payment method)

```http
POST https://api-sandbox.amos.com/setup_intents
X-Api-Key: $AMOS_API_KEY
X-Api-Version: 1
Content-Type: application/json

{
  "setup_intent": {
    "customer_id": "optional-uuid"
  }
}
```

Same `EmbedToken` response; browser confirms with `await confirmSetup`. Setup intents are organization-scoped (`X-Account-Id` ignored). The JWT carries `organization_id` + `setup_intent_id`.

### Customer (optional)

```http
POST https://api-sandbox.amos.com/customers
X-Api-Key: $AMOS_API_KEY
X-Api-Version: 1
Content-Type: application/json

{
  "customer": { "email": "customer@example.com" }
}
```

Use returned `id` as `payment_intent.customer_id` / `setup_intent.customer_id`.

## Server: TypeScript (`@amos.com/node`)

```ts
import {
  createPayApiClient,
  AMOS_API_BASE_URL_SANDBOX,
  AMOS_API_VERSION,
} from "@amos.com/node";
import type { components } from "@amos.com/node";

const pay = createPayApiClient({
  baseUrl: AMOS_API_BASE_URL_SANDBOX,
  headers: {
    "X-Api-Key": process.env.AMOS_API_KEY!,
    "X-Api-Version": AMOS_API_VERSION,
  },
});

export async function createPaymentIntent(input: {
  /** Integer cents (e.g. `5000` for $50.00). */
  amount: number;
  customerId?: string;
  email?: string;
}) {
  let customerId = input.customerId;

  if (!customerId && input.email) {
    const customerRes = await pay.POST("/customers", {
      body: { customer: { email: input.email } },
    });
    if (customerRes.error || !customerRes.data?.id) {
      throw new Error("Failed to create customer");
    }
    customerId = customerRes.data.id;
  }

  const body: components["schemas"]["CreatePaymentIntentRequest"] = {
    payment_intent: {
      amount: input.amount,
      capture_method: "automatic",
      ...(customerId ? { customer_id: customerId } : {}),
    },
  };

  const { data, error } = await pay.POST("/payment_intents", { body });
  if (error || !data?.token) throw new Error("Failed to create payment intent");

  return { token: data.token };
}

export async function createSetupIntent(input: { customerId?: string }) {
  const body: components["schemas"]["CreateSetupIntentRequest"] = {
    setup_intent: {
      ...(input.customerId ? { customer_id: input.customerId } : {}),
    },
  };

  const { data, error } = await pay.POST("/setup_intents", { body });
  if (error || !data?.token) throw new Error("Failed to create setup intent");

  return { token: data.token };
}
```

## React: card payment intent

Wrap the component in a host `<form>`. Enter in the iframe submits it (the parent cannot listen for that key). Pay button must be `type="submit"`.

```tsx
import { useRef, useState } from "react";
import {
  AmosCreditCardPaymentMethodForm,
  type ConfirmPaymentResult,
  confirmPayment,
  focusField,
  isConfirmTimeout,
  resetForm,
  validateForm,
} from "@amos.com/react-amos-js";

export function CardPaymentForm({ renderToken }: { renderToken: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isValid, setIsValid] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function onPayAgain() {
    setDone(false);
    setError(null);
    resetForm({ iframeRef });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setProcessing(true);
    setError(null);

    try {
      const valid = await validateForm({ iframeRef });
      if (!valid) {
        setError("Please complete the card form.");
        setProcessing(false);
        return;
      }

      const res = await fetch("/api/payment-intents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: 5000, email: "customer@example.com" }), // $50.00 in cents
      });
      if (!res.ok) throw new Error("Could not start payment.");

      const { token } = (await res.json()) as { token: string };
      const result: ConfirmPaymentResult = await confirmPayment({ iframeRef, token });
      if (isConfirmTimeout(result)) {
        setError("Payment is taking longer than expected. Do not retry yet.");
        return;
      }
      if (result.status === "succeeded") {
        setDone(true);
        return;
      }
      // declined / validation: field errors stay in the iframe; unlock UI
      setError("Payment failed. Please try again.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setProcessing(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <AmosCreditCardPaymentMethodForm
        ref={iframeRef}
        renderToken={renderToken}
        additionalFields={{ cardholderName: true }}
        defaultValues={{
          name: "Alex Example",
          billingAddress: { country: "US", postalCode: "90210" },
        }}
        onValidityChange={({ isValid }) => setIsValid(isValid)}
        onCardBrandChanged={({ brand }) => {
          // "visa" | "mastercard" | "amex" | "discover" | "diners" | "jcb" | null
        }}
      />
      <button type="button" onClick={() => focusField({ iframeRef, field: "cardNumber" })}>
        Edit card
      </button>
      {error ? <p role="alert">{error}</p> : null}
      {done ? (
        <p>
          Payment succeeded.{" "}
          <button type="button" onClick={onPayAgain}>Pay again</button>
        </p>
      ) : null}
      <button type="submit" disabled={!isValid || processing || done}>
        {processing ? "Processing…" : "Pay now"}
      </button>
    </form>
  );
}
```

## React: setup intent (save card)

Same form; different server route + `confirmSetup`.

```tsx
import { useRef, useState } from "react";
import {
  AmosCreditCardPaymentMethodForm,
  confirmSetup,
  validateForm,
} from "@amos.com/react-amos-js";

export function SaveCardForm({ renderToken }: { renderToken: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setProcessing(true);
    setError(null);

    try {
      if (!(await validateForm({ iframeRef }))) {
        setError("Please complete the card form.");
        setProcessing(false);
        return;
      }

      const res = await fetch("/api/setup-intents", { method: "POST" });
      if (!res.ok) throw new Error("Could not start setup.");

      const { token } = (await res.json()) as { token: string };
      const result = await confirmSetup({ iframeRef, token });
      if (result.status !== "succeeded") {
        setError("Failed to save the payment method.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setProcessing(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <AmosCreditCardPaymentMethodForm
        ref={iframeRef}
        renderToken={renderToken}
      />
      {error ? <p role="alert">{error}</p> : null}
      <button type="submit" disabled={processing}>
        {processing ? "Saving…" : "Save card"}
      </button>
    </form>
  );
}
```

## React: bank payment intent (Plaid / ACH)

For payment intents, pass `requireAchVerification` when your host-side rule requires **Plaid Embedded Institution Search**. For setup (save bank), pass `intent="setup"` — that always shows Plaid unless the render token disables verification. The SDK shows a 350px pulse skeleton until Plaid’s `onLoad` — do not overlay a host loader.

Parent pages that may hit Plaid need CSP: `script-src https://cdn.plaid.com` and `frame-src https://js.amos.com https://js-sandbox.amos.com https://cdn.plaid.com https://*.plaid.com`. Do not mint link tokens or load Plaid yourself.

```tsx
import { useRef, useState } from "react";
import {
  AmosBankAccountPaymentMethodForm,
  confirmPayment,
  validateForm,
} from "@amos.com/react-amos-js";

export function BankPaymentForm({ renderToken }: { renderToken: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isValid, setIsValid] = useState(false);
  const [processing, setProcessing] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setProcessing(true);
    try {
      if (!(await validateForm({ iframeRef }))) {
        setProcessing(false);
        return;
      }
      const res = await fetch("/api/payment-intents", { method: "POST" });
      const { token } = (await res.json()) as { token: string };
      await confirmPayment({ iframeRef, token });
    } finally {
      setProcessing(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <AmosBankAccountPaymentMethodForm
        ref={iframeRef}
        renderToken={renderToken}
        requireAchVerification
        // intent="setup" // save a bank account — always Plaid unless verification is disabled
        onValidityChange={({ isValid }) => setIsValid(isValid)}
      />
      <button type="submit" disabled={!isValid || processing}>
        {processing ? "Processing…" : "Pay with bank"}
      </button>
    </form>
  );
}
```

## React: Google Pay / Apple Pay (express)

Wallet button `amount` is a **major-currency decimal string** (`"50.00"` for $50.00), not cents. The iframe converts it to cents in `paymentIntentCreateAttributes.amount` — forward those attributes to your Pay API create call as `{ payment_intent }` as-is.

Create the intent inside **`onConfirm`**, then **`return confirmPayment(token)`**. The SDK does not auto-confirm. Type `customerCreateAttributes` as **`WalletCustomerCreateAttributes`**, not `CreateCustomerInput`. Map nested `billingAddress` (`address_line1` / `state` / `postal_code`) on the server. Name, email, and billing are always collected; pass top-level `phoneRequired` / `shippingAddressRequired` (default `false`) when you need phone or shipping. Do not put those flags in `buttonProps`.

```tsx
import { useState } from "react";
import {
  AmosGooglePayButton,
  AmosApplePayButton,
  isConfirmTimeout,
  type ConfirmPaymentResult,
  type WalletCustomerCreateAttributes,
} from "@amos.com/react-amos-js";
import type { components } from "@amos.com/node";

export function ExpressButtons({ renderToken }: { renderToken: string }) {
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm({
    paymentIntentCreateAttributes,
    customerCreateAttributes,
    confirmPayment,
  }: {
    paymentIntentCreateAttributes: components["schemas"]["CreatePaymentIntentInput"];
    customerCreateAttributes: WalletCustomerCreateAttributes;
    confirmPayment: (token: string) => Promise<ConfirmPaymentResult>;
  }): Promise<ConfirmPaymentResult> {
    try {
      const res = await fetch("/api/payment-intents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // Map WalletCustomerCreateAttributes on the server — it is not
          // CreateCustomerInput.
          paymentIntent: paymentIntentCreateAttributes,
          customer: customerCreateAttributes,
        }),
      });
      if (!res.ok) throw new Error("Failed to create payment intent.");
      const { token } = (await res.json()) as { token: string };
      const result = await confirmPayment(token);
      if (isConfirmTimeout(result)) {
        setError("Payment is taking longer than expected. Do not retry yet.");
      } else if (result.status === "failed") {
        setError("Payment failed. Please try again.");
      }
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      return { status: "failed" };
    }
  }

  return (
    <>
      <AmosGooglePayButton
        renderToken={renderToken}
        amount="50.00"
        merchantName="Example Store"
        phoneRequired
        buttonProps={{ buttonType: "pay" }}
        iframeProps={{ style: { borderRadius: "8px" } }}
        onConfirm={handleConfirm}
      />
      <AmosApplePayButton
        renderToken={renderToken}
        amount="50.00"
        merchantName="Example Store"
        phoneRequired
        buttonProps={{ buttonstyle: "black", type: "buy" }}
        iframeProps={{ style: { borderRadius: "8px" } }}
        onConfirm={handleConfirm}
      />
      {error ? <p role="alert">{error}</p> : null}
    </>
  );
}
```

Apple Pay: Safari uses the native sheet; other browsers open Apple's QR popup. The SDK shows a waiting overlay with **Cancel payment** until the buyer authorizes, then **Completing your payment…** (no Cancel) until `onConfirm` settles — no host expand/collapse code needed.

## React: method tabs (keep mounted)

Mount every method you offer. Hide inactive panels with CSS — do not unmount on tab change (that reloads the iframe and re-shows the skeleton). Wrap the mounts in a host `<form>` so Enter in either iframe still submits.

```tsx
const [method, setMethod] = useState<"card" | "bank">("card");

return (
  <form onSubmit={onSubmit}>
    <button type="button" onClick={() => setMethod("card")}>Card</button>
    <button type="button" onClick={() => setMethod("bank")}>Bank</button>
    <div hidden={method !== "card"}>
      <AmosCreditCardPaymentMethodForm
        ref={cardRef}
        renderToken={renderToken}
      />
    </div>
    <div hidden={method !== "bank"}>
      <AmosBankAccountPaymentMethodForm
        ref={bankRef}
        renderToken={renderToken}
      />
    </div>
    <button type="submit">Pay</button>
  </form>
);
```

Confirm/validate against the selected method’s `iframeRef`.

## Vanilla: card payment intent

Mount **inside a host `<form>`**. Enter in the iframe submits it (same as Stripe Elements). Listen to `submit`, not only a button `click`.

```ts
import {
  mountAmosCreditCardPaymentMethodForm,
  validateForm,
  confirmPayment,
  isConfirmTimeout,
  resetForm,
} from "@amos.com/amos-js";

const card = mountAmosCreditCardPaymentMethodForm("#card-form", {
  renderToken: RENDER_TOKEN,
  additionalFields: { cardholderName: true },
  onValidityChange: ({ isValid }) => {
    document.querySelector("#pay")!.toggleAttribute("disabled", !isValid);
  },
  onCardBrandChanged: ({ brand }) => {
    // "visa" | "mastercard" | "amex" | "discover" | "diners" | "jcb" | null
  },
});

document.querySelector("#checkout")!.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!(await validateForm({ iframe: card.iframe }))) return;
  const { token } = await fetch("/api/payment-intents", { method: "POST" }).then(
    (r) => r.json(),
  );
  const result = await confirmPayment({ iframe: card.iframe, token });
  if (isConfirmTimeout(result)) {
    // Uncertain — do not retry as a new payment
    return;
  }
  if (result.status === "succeeded") {
    // Optional: resetForm({ iframe: card.iframe }) before another payment
  }
});
```

## Vanilla: Google Pay / Apple Pay

```ts
import {
  mountAmosApplePayButton,
  mountAmosGooglePayButton,
  type ConfirmPaymentResult,
  type WalletCustomerCreateAttributes,
} from "@amos.com/amos-js";
import type { components } from "@amos.com/node";

const shared = {
  renderToken: RENDER_TOKEN,
  amount: "50.00",
  merchantName: "Example Store",
  phoneRequired: true,
  onConfirm: async ({
    paymentIntentCreateAttributes,
    customerCreateAttributes,
    confirmPayment,
  }: {
    paymentIntentCreateAttributes: components["schemas"]["CreatePaymentIntentInput"];
    customerCreateAttributes: WalletCustomerCreateAttributes;
    confirmPayment: (token: string) => Promise<ConfirmPaymentResult>;
  }): Promise<ConfirmPaymentResult> => {
    const response = await fetch("/api/payment-intents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        // Map WalletCustomerCreateAttributes on the server — it is not
        // CreateCustomerInput.
        customer: customerCreateAttributes,
        paymentIntent: paymentIntentCreateAttributes,
      }),
    });
    const { token } = (await response.json()) as { token: string };
    return confirmPayment(token);
  },
};

mountAmosGooglePayButton("#google-pay", shared);
mountAmosApplePayButton("#apple-pay", shared);
```

## Vanilla: bank (Plaid / ACH)

The SDK shows a 350px pulse skeleton until Plaid’s `onLoad`. Do not overlay a host loader.

```ts
import { mountAmosBankAccountPaymentMethodForm } from "@amos.com/amos-js";

const bank = mountAmosBankAccountPaymentMethodForm("#bank-form", {
  renderToken: RENDER_TOKEN,
  requireAchVerification: true,
  // intent: "setup", // save a bank account — always Plaid unless verification is disabled
  defaultValues: {
    name: "Alex Example",
    billingAddress: { country: "US", postalCode: "90210" },
  },
  onValidityChange: ({ isValid }) => {
    document.querySelector("#pay")!.toggleAttribute("disabled", !isValid);
  },
});

bank.update({ requireAchVerification: false });
bank.focus("accountHolderName");
```

## Appearance

```tsx
appearance={{
  labels: "floating",
  fonts: [
    {
      cssSrc:
        "https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap",
    },
  ],
  themeVariables: {
    "--primary": "oklch(0.5 0.2 240)",
    "--radius": "0.5rem",
    "--font-family": "Inter, ui-sans-serif, system-ui, sans-serif",
  },
  rules: {
    ".Label": { fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" },
    ".Input--invalid": { boxShadow: "0 0 0 2px oklch(0.55 0.245 27.325)" },
  },
}}
```

Pair `fonts` with `--font-family`. Omit both on first paint to get Inter. `fonts: []` skips the webfont (system stack). `themeVariables` **replaces** the override set — restating `{ "--primary": "…" }` drops other keys (omitted `--font-family` is filled with Inter). Wallet buttons do not take `appearance`.

Modal: pass `onEscapeKeyPressed` on the card/bank component so Escape inside the iframe can close it.
