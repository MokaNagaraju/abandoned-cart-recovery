# Data Dictionary – Abandoned Cart Recovery Synthetic Dataset

**Seed:** `20261022`  
**Generator version:** 1.0  
**Scale parameter:** Controls volume (1.0 = full production volumes)

All IDs are immutable strings following the prescribed nomenclature.  
All timestamps are ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).  
Monetary values use `DECIMAL(12,2)` semantics (stored as float64 for generation, rounded to 2 decimals).

---

## 1. Customer

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| customer_id      | string        | yes      | `CUS-000001` … zero-padded 6 digits             | PK         | Matches pattern `^CUS-\d{6}$` |
| email            | string        | yes      | valid email format                              | unique     | Lowercase, contains `@` |
| phone            | string        | no       | E.164-like `+1XXXXXXXXXX`                       |            | Optional |
| first_name       | string        | yes      |                                                 |            | Non-empty |
| last_name        | string        | yes      |                                                 |            | Non-empty |
| country_code     | string        | yes      | ISO-3166-1 alpha-2 (US, IN, GB, …)              |            | 2 uppercase letters |
| created_at       | datetime      | yes      |                                                 |            | ≤ now |
| is_active        | boolean       | yes      | true / false                                    |            | |

**Cardinality:** 1 Customer → N Consent, N Session, N Cart, N Order

---

## 2. Consent

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| consent_id       | string        | yes      | `CON-000001` …                                  | PK         | |
| customer_id      | string        | yes      | FK → Customer                                   |            | Must exist |
| channel          | string        | yes      | `email`, `sms`                                  |            | Enum |
| status           | string        | yes      | `opt_in`, `opt_out`                             |            | Enum |
| effective_from   | datetime      | yes      |                                                 |            | |
| effective_to     | datetime      | no       | null = still active                             |            | ≥ effective_from if present |
| source           | string        | yes      | `registration`, `preference_center`, `campaign_unsubscribe`, `support` | | |

**Cardinality:** 1 Customer → N Consent (history preserved; latest by effective_from wins for a channel)

---

## 3. Session

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| session_id       | string        | yes      | `SES-000001` …                                  | PK         | |
| customer_id      | string        | no       | FK → Customer (null = anonymous)                |            | |
| device_id        | string        | yes      | `DEV-xxxxxxxx`                                  |            | |
| started_at       | datetime      | yes      |                                                 |            | |
| ended_at         | datetime      | no       |                                                 |            | ≥ started_at |
| user_agent       | string        | yes      | simplified                                      |            | |

**Cardinality:** 1 Customer → N Session; 1 Session → 0..N Cart

---

## 4. Cart

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| cart_id          | string        | yes      | `CART-2026-000001` …                            | PK         | Pattern `^CART-2026-\d{6}$` |
| customer_id      | string        | yes      | FK → Customer                                   |            | Must exist |
| session_id       | string        | yes      | FK → Session                                    |            | Must exist |
| status           | string        | yes      | `active`, `abandoned`, `recovered`, `converted` |            | Enum |
| created_at       | datetime      | yes      |                                                 |            | |
| last_updated_at  | datetime      | yes      |                                                 |            | ≥ created_at |
| abandoned_at     | datetime      | no       | set when status becomes abandoned               |            | ≥ last_updated_at |
| currency         | string        | yes      | `USD`, `INR`, `EUR`, `GBP`                      |            | |
| total_amount     | decimal(12,2) | yes      | sum of CartLine.line_total (derived)            |            | ≥ 0, 2 decimals |

**Cardinality:** 1 Cart → N CartLine; 1 Cart → 0..1 Order (via conversion)

**Abandonment rule (deterministic):**  
A cart becomes `abandoned` if:
- `last_updated_at` + `ABANDONMENT_WINDOW_HOURS` (default 1 h) has passed, **and**
- no Order exists that references this cart_id, **and**
- status was still `active`.

---

## 5. CartLine

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| cart_line_id     | string        | yes      | `CLN-000001` …                                  | PK         | |
| cart_id          | string        | yes      | FK → Cart                                       |            | Must exist |
| product_id       | string        | yes      | `PRD-0001` …                                    |            | |
| product_name     | string        | yes      |                                                 |            | |
| quantity         | integer       | yes      | ≥ 1                                             |            | |
| unit_price       | decimal(12,2) | yes      | ≥ 0                                             |            | |
| line_total       | decimal(12,2) | yes      | quantity × unit_price (derived)                 |            | |
| updated_at       | datetime      | yes      |                                                 |            | |

**Cardinality:** 1 Cart → N CartLine (1..N)

---

## 6. Campaign

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| campaign_id      | string        | yes      | `CMP-2026-000001` …                             | PK         | Pattern `^CMP-2026-\d{6}$` |
| name             | string        | yes      |                                                 |            | |
| channel          | string        | yes      | `email`, `sms`                                  |            | |
| variant          | string        | yes      | `A`, `B`, `C`                                   |            | |
| start_at         | datetime      | yes      |                                                 |            | |
| end_at           | datetime      | yes      |                                                 |            | ≥ start_at |
| status           | string        | yes      | `draft`, `active`, `completed`, `paused`        |            | |

---

## 7. MessageTemplate

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| template_id      | string        | yes      | `TPL-000001` …                                  | PK         | |
| campaign_id      | string        | yes      | FK → Campaign                                   |            | |
| channel          | string        | yes      | `email`, `sms`                                  |            | Must match campaign |
| subject          | string        | no       | required for email                              |            | |
| body             | string        | yes      |                                                 |            | |
| variant          | string        | yes      | `A`, `B`, `C`                                   |            | |

---

## 8. SendAttempt

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| send_id          | string        | yes      | `SEND-2026-000001` …                            | PK         | Pattern `^SEND-2026-\d{6}$` |
| cart_id          | string        | yes      | FK → Cart                                       |            | Must be abandoned |
| campaign_id      | string        | yes      | FK → Campaign                                   |            | |
| template_id      | string        | yes      | FK → 
MessageTemplate                            |            | |
| message_id       | string        | yes      | `MSG-<cart_id>-NN`, NN = `01` (first message), `02`, `03` (follow-ups), e.g. `MSG-CART-2026-000415-02` | unique | Must equal `MSG-` + cart_id + `-` + 2-digit sequence; at most `MAX_MESSAGES_PER_CART` (3) per cart |
| customer_id      | string        | yes      | FK → Customer                                   |            | |
| channel          | string        | yes      | `email`, `sms`                                  |            | |
| scheduled_at     | datetime      | yes      |                                                 |            | |
| sent_at          | datetime      | no       | null if suppressed                              |            | ≥ scheduled_at |
| status           | string        | yes      | `scheduled`, `sent`, `delivered`, `opened`, `clicked`, `bounced`, `suppressed` | | Enum |
| suppression_reason | string     | no       | `opt_out`, `frequency_cap`, `already_converted`, `invalid_consent`, null | | |

**Business rules enforced before send:**
1. Latest Consent for (customer, channel) must be `opt_in`.
2. Frequency cap: ≤ `MAX_SENDS_PER_CUSTOMER_PER_WINDOW` (default 2) non-suppressed sends per customer **per channel** in the `FREQUENCY_WINDOW_DAYS` (default 7) before the scheduled time. A 3rd message inside that window is stored as `status=suppressed`, `suppression_reason=frequency_cap` (a frequency-cap conflict).
3. Cart must still be abandoned (not recovered/converted). Follow-ups scheduled at or after the cart's order are stored as `suppressed` / `already_converted`.

**Follow-up messages:** after message `01`, a cart gets message `02` with probability `P_FOLLOWUP_1` (0.40) and then `03` with probability `P_FOLLOWUP_2` (0.30), each `FOLLOWUP_GAP_HOURS` (24–48 h) after the previous one. Follow-ups use a different campaign/variant on the same channel when one exists. A message suppressed for `opt_out` ends the chain.

**Event history:** the final `status` on SendAttempt is a convenience summary. Full progression is stored append-only in `message_events` (sent → delivered → opened → clicked, or bounced).

---

## 9. MessageEvent

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| event_id         | string        | yes      | `EVT-000001` …                                  | PK         | |
| send_id          | string        | yes      | FK → SendAttempt                                |            | Must exist |
| event_type       | string        | yes      | `sent`, `delivered`, `opened`, `clicked`, `bounced` |        | Enum |
| event_at         | datetime      | yes      |                                                 |            | ≥ send.scheduled_at |

**Cardinality:** 1 SendAttempt → 0..N MessageEvent (suppressed sends have none)

---

## 10. Order

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| order_id         | string        | yes      | `ORD-2026-000001` …                             | PK         | Pattern `^ORD-2026-\d{6}$` |
| customer_id      | string        | yes      | FK → Customer                                   |            | |
| cart_id          | string        | no       | FK → Cart (null = organic order)                |            | |
| order_at         | datetime      | yes      |                                                 |            | |
| total_amount     | decimal(12,2) | yes      | ≥ 0                                             |            | |
| currency         | string        | yes      |                                                 |            | |
| status           | string        | yes      | `pending`, `paid`, `shipped`, `cancelled`       |            | |

---

## 11. Attribution

| Field            | Type          | Required | Allowed Values / Notes                          | Uniqueness | Validation Rule |
|------------------|---------------|----------|--------------------------------------------------|------------|-----------------|
| attribution_id   | string        | yes      | `ATT-000001` …                                  | PK         | |
| order_id         | string        | yes      | FK → Order                                      |            | |
| send_id          | string        | yes      | FK → SendAttempt                                |            | |
| campaign_id      | string        | yes      | FK → Campaign                                   |            | |
| attributed_amount| decimal(12,2) | yes      | portion of order attributed                     |            | ≥ 0 |
| attribution_window_hours | integer | yes   | documented window used                          |            | |
| is_primary       | boolean       | yes      | true for the winning attribution                |            | Exactly one primary per order when attributed |

**Attribution rule (deterministic):**  
An Order is attributed to a SendAttempt if:
- Order.order_at is within `ATTRIBUTION_WINDOW_HOURS` (default 168 = 7 days) after SendAttempt.sent_at (or open/click if recorded),
- the SendAttempt status reached at least `opened` or `clicked` (configurable),
- and the customer matches.

When multiple qualifying sends exist (status `opened`/`clicked`, sent before the order and within `ATTRIBUTION_WINDOW_HOURS`), the **most recent** one for the same cart is chosen as primary (`is_primary=true`) – deterministic last-touch. Others may be recorded with `is_primary=false` for audit (edge-case “double-count” scenarios are labelled in ground_truth).

---

## Ground Truth Labels (`ground_truth.csv`)

| Field            | Type     | Notes |
|------------------|----------|-------|
| entity_type      | string   | `SendAttempt`, `Cart`, `Attribution`, … |
| entity_id        | string   | ID of the anomalous record |
| issue_type       | string   | See required edge cases below |
| description      | string   | Human-readable explanation |
| expected_decision| string   | What the system should have done / correct label |

**Required edge-case issue_types:**
- `message_sent_after_opt_out`
- `cart_abandoned_after_purchase`
- `attribution_double_counted`
- `cart_total_stale_after_quantity_update`

---

## Derived / Calculated Fields (never independently random)

- `Cart.total_amount` = Σ `CartLine.line_total`
- `CartLine.line_total` = `quantity × unit_price`
- Abandonment timestamps and status transitions follow the rules above
- Attribution decisions follow the deterministic window + most-recent rule
- Consent checks always use the latest effective Consent record for the channel

---

## Lifecycle States & Transitions

**Cart status transitions (forward only):**  
`active` → `abandoned` → (`recovered` | `converted`)

**SendAttempt status progression (typical):**  
`scheduled` → `sent` → `delivered` → `opened` → `clicked`  
or early exit to `suppressed` / `bounced`

All state changes are recorded as new events or explicit fields; history is never overwritten.
