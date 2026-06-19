# Webhook setup for CRM integration

## Environment variables

- `WEBHOOK_ENABLED=true`
- `WEBHOOK_URL=https://crm.example.com/webhook/surveybot`
- `WEBHOOK_SECRET=your_secret_key`

## Payload format

```json
{
  "event_type": "new_response",
  "timestamp": "2026-06-19T13:00:00+00:00",
  "data": {
    "response_id": 1,
    "survey_id": 2,
    "user_id": 123456789
  }
}
```

## Signature validation

Signature is sent in header: `X-SurveyBot-Signature`

Compute HMAC-SHA256 using `WEBHOOK_SECRET` and raw request body.

### Python example

```python
import hashlib
import hmac

def is_valid(signature_header: str, raw_body: bytes, secret: str) -> bool:
    calc = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, signature_header)
```

### Node.js example

```javascript
const crypto = require("crypto");
function isValid(signature, rawBody, secret) {
  const calc = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(calc), Buffer.from(signature));
}
```

### PHP example

```php
<?php
function is_valid($signature, $rawBody, $secret) {
    $calc = hash_hmac('sha256', $rawBody, $secret);
    return hash_equals($calc, $signature);
}
```
