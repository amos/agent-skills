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

Same `EmbedToken` response; browser confirms with `confirmSetupIntent`.

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

```tsx
import { useRef, useState } from "react";
import {
  AmosCreditCardPaymentMethodForm,
  confirmPaymentIntent,
  resetForm,
  validateForm,
} from "@amos.com/react-amos-js";
import type { ConfirmationResult } from "@amos.com/react-amos-js";

export function CardPaymentForm({ renderToken }: { renderToken: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isValid, setIsValid] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function handleResult(result: ConfirmationResult) {
    setProcessing(false);
    if (result.status === "succeeded") {
      setDone(true);
      return;
    }
    if (result.status === "failed") {
      setError(result.errorMessage);
      return;
    }
    // incomplete: field_errors | validation_failed — shown in iframe; unlock UI
    setError(null);
  }

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
      confirmPaymentIntent({ iframeRef, token });
      // Keep processing until onResult
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setProcessing(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <AmosCreditCardPaymentMethodForm
        ref={iframeRef}
        renderToken={renderToken}
        additionalFields={{ cardholderName: true }}
        onValidityChange={({ isValid }) => setIsValid(isValid)}
        onResult={handleResult}
      />
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

Same form; different server route + confirm helper. `onResult` with `intent: "setup"` on success.

```tsx
import { useRef, useState } from "react";
import {
  AmosCreditCardPaymentMethodForm,
  confirmSetupIntent,
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
      confirmSetupIntent({ iframeRef, token });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setProcessing(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <AmosCreditCardPaymentMethodForm
        ref={iframeRef}
        renderToken={renderToken}
        onResult={(result) => {
          setProcessing(false);
          if (result.status === "failed") setError(result.errorMessage);
        }}
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

Bank `amount` is a **major-currency decimal string** (`"50.00"` for $50.00), same as wallets. Omit it for setup intents or when the charge is unknown — if a threshold is set, the SDK shows **Connect bank account** (Plaid Link) instead of routing/account fields.

Parent pages that may hit Plaid need CSP: `script-src https://cdn.plaid.com` and `frame-src https://cdn.plaid.com https://*.plaid.com`. Do not mint link tokens or load Plaid yourself.

```tsx
import { useRef, useState } from "react";
import {
  AmosBankAccountPaymentMethodForm,
  confirmPaymentIntent,
  validateForm,
} from "@amos.com/react-amos-js";
import type { ConfirmationResult } from "@amos.com/react-amos-js";

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
      confirmPaymentIntent({ iframeRef, token });
    } catch {
      setProcessing(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <AmosBankAccountPaymentMethodForm
        ref={iframeRef}
        renderToken={renderToken}
        amount="50.00"
        onValidityChange={({ isValid }) => setIsValid(isValid)}
        onResult={(result: ConfirmationResult) => {
          setProcessing(false);
          if (result.status === "failed") console.error(result.errorMessage);
        }}
      />
      <button type="submit" disabled={!isValid || processing}>
        {processing ? "Processing…" : "Pay with bank"}
      </button>
    </form>
  );
}
```

## React: Google Pay / Apple Pay (express)

Wallet button `amount` is a **major-currency decimal string** (`"50.00"` for $50.00), not cents. The iframe converts it to cents in `paymentIntentCreateAttributes.amount` — forward those attributes to your Pay API create call as-is.

```tsx
import { useState } from "react";
import { AmosGooglePayButton, AmosApplePayButton } from "@amos.com/react-amos-js";

export function ExpressButtons({ renderToken }: { renderToken: string }) {
  const [error, setError] = useState<string | null>(null);

  const initiate = async ({
    paymentIntentCreateAttributes,
    customerCreateAttributes,
  }: {
    paymentIntentCreateAttributes: unknown;
    customerCreateAttributes: unknown;
  }) => {
    const res = await fetch("/api/payment-intents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paymentIntent: paymentIntentCreateAttributes,
        customer: customerCreateAttributes,
      }),
    });
    if (!res.ok) throw new Error("Failed to create payment intent.");
    const { token } = (await res.json()) as { token: string };
    return token;
  };

  return (
    <>
      <AmosGooglePayButton
        renderToken={renderToken}
        amount="50.00"
        merchantName="Example Store"
        buttonProps={{ buttonType: "pay" }}
        iframeProps={{ style: { borderRadius: "8px" } }}
        onInitiatePaymentIntentRequest={initiate}
        onResult={(result) => {
          if (result.status === "failed") setError(result.errorMessage);
        }}
      />
      <AmosApplePayButton
        renderToken={renderToken}
        amount="50.00"
        merchantName="Example Store"
        buttonProps={{ buttonstyle: "black", type: "buy" }}
        iframeProps={{ style: { borderRadius: "8px" } }}
        onInitiatePaymentIntentRequest={initiate}
        onResult={(result) => {
          if (result.status === "failed") setError(result.errorMessage);
        }}
      />
      {error ? <p role="alert">{error}</p> : null}
    </>
  );
}
```

Apple Pay: Safari uses the native sheet; other browsers open Apple's QR popup. The SDK shows a waiting overlay with Cancel — no host expand/collapse code needed.

## React: method tabs (keep mounted)

Mount every method you offer. Hide inactive panels with CSS — do not unmount on tab change (that reloads the iframe and re-shows the skeleton).

```tsx
const [method, setMethod] = useState<"card" | "bank">("card");

return (
  <>
    <button type="button" onClick={() => setMethod("card")}>Card</button>
    <button type="button" onClick={() => setMethod("bank")}>Bank</button>
    <div hidden={method !== "card"}>
      <AmosCreditCardPaymentMethodForm
        ref={cardRef}
        renderToken={renderToken}
        onResult={handleResult}
      />
    </div>
    <div hidden={method !== "bank"}>
      <AmosBankAccountPaymentMethodForm
        ref={bankRef}
        renderToken={renderToken}
        onResult={handleResult}
      />
    </div>
  </>
);
```

Confirm/validate against the selected method’s `iframeRef`.

## Vanilla: card payment intent

```ts
import {
  mountAmosCreditCardPaymentMethodForm,
  validateForm,
  confirmPaymentIntent,
  resetForm,
} from "@amos.com/amos-js";

const form = mountAmosCreditCardPaymentMethodForm("#card-form", {
  renderToken: RENDER_TOKEN,
  additionalFields: { cardholderName: true },
  onValidityChange: ({ isValid }) => {
    document.querySelector("#pay")!.toggleAttribute("disabled", !isValid);
  },
  onResult: (result) => {
    if (result.status === "succeeded") {
      console.log(result.paymentIntent.id);
      // Optional: resetForm({ iframe: form.iframe }) before another payment
    } else if (result.status === "failed") console.error(result.errorMessage);
    else if (result.status === "incomplete") console.log(result.reason);
  },
});

document.querySelector("#pay")!.addEventListener("click", async () => {
  if (!(await validateForm({ iframe: form.iframe }))) return;
  const { token } = await fetch("/api/payment-intents", { method: "POST" }).then(
    (r) => r.json(),
  );
  confirmPaymentIntent({ iframe: form.iframe, token });
});
```

## Vanilla: bank (Plaid / ACH)

```ts
import { mountAmosBankAccountPaymentMethodForm } from "@amos.com/amos-js";

const bank = mountAmosBankAccountPaymentMethodForm("#bank-form", {
  renderToken: RENDER_TOKEN,
  amount: "50.00", // omit to always Connect once a threshold exists
  onValidityChange: ({ isValid }) => {
    document.querySelector("#pay")!.toggleAttribute("disabled", !isValid);
  },
  onResult: (result) => {
    /* same as card */
  },
});

bank.update({ amount: "25.00" });
```

## Appearance

```tsx
appearance={{
  labels: "floating",
  themeVariables: {
    "--primary": "oklch(0.5 0.2 240)",
    "--radius": "0.5rem",
  },
}}
```
