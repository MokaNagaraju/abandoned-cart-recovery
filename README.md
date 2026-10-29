# Abandoned Cart Recovery – Synthetic Data Generator

**YottaFlex AI – 72-Hour Code Challenge**  
Candidate: Moka Naga Raju

This repository produces a complete, reproducible, multi-entity synthetic dataset that implements the end-to-end abandoned-cart recovery workflow:

- Identify abandoned carts (time-based inactivity window)
- Respect contact consent and frequency caps
- Coordinate personalized recovery campaigns (email / SMS)
- Attribute subsequent conversions within a documented window
- Preserve full event history and expose decisions / exceptions
- Deliver measurable outputs + separate ground-truth labels for anomalies

---

## Transparency & Safety

- AI use and prompt history: see `docs/AI_USE.md` and `docs/prompt_history.md`.
- Data is 100% synthetic. Emails use `example.com`, phone numbers are random, and names come from the Faker library.
- The repo contains no secrets, credentials, API keys or proprietary code. No configuration needs secrets; all settings are in `src/config.py`.
- Setup and run steps are in "Quick Start" below.
- At `--scale 1.0` the generator targets exactly 20 000 abandoned carts and the configured edge-case counts.
- `seed.sql` holds a 100-row sample per table; full data is in CSV/JSON.
- See "Coverage Status" below for the complete feature checklist.

---

## Quick Start (Laptop)

### 1. Prerequisites

- Python 3.10+
- ~2 GB free disk space for the full dataset (scale=1.0)

### 2. Clone & Install

```bash
git clone <your-public-repo-url>
cd abandoned-cart-recovery

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Generate a small demo dataset (recommended first run)

```bash
python -m src.generator --scale 0.02 --out data/demo
```

This creates ~1 000 carts in a few seconds.

### 4. Generate the full requested volume

```bash
python -m src.generator --full --out data/full
# equivalent to --scale 1.0
```

Expected approximate volumes at scale=1.0:

| Entity            | Rows (approx.) |
|-------------------|----------------|
| Customers         | 35 000         |
| Consents          | ~70 000+       |
| Sessions          | 50 000         |
| Carts             | 50 000         |
| Cart Lines        | ~150 000       |
| Campaigns         | 40             |
| Message Templates | 40             |
| Send Attempts     | ~10 015 (10 000 baseline incl. follow-ups and suppressed + injected anomalies) |
| Orders            | ~1 300         |
| Attributions      | ~785 (incl. 15 labelled double-counts) |
| Ground Truth      | ~79            |

### 5. Reproducibility check

```bash
python -m src.generator --scale 0.05 --out data/run1
python -m src.generator --scale 0.05 --out data/run2
# Compare checksums in data/run1/manifest.json vs data/run2/manifest.json
# They must be identical when the seed is the same.
```

---

## Output Layout

```
data/<run>/
├── csv/                    # One CSV per entity
│   ├── customers.csv
│   ├── consents.csv
│   ├── sessions.csv
│   ├── carts.csv
│   ├── cart_lines.csv
│   ├── campaigns.csv
│   ├── message_templates.csv
│   ├── send_attempts.csv
│   ├── message_events.csv
│   ├── orders.csv
│   ├── attributions.csv
│   └── ground_truth.csv
├── json/                   # Same data as JSON arrays
├── seed.sql                # Sample INSERT statements (100 rows per table)
├── manifest.json           # Row counts + SHA-256 checksums + validation report
└── validation_summary.txt
```

---

## Business Rules Implemented (Deterministic)

| Rule                        | Implementation |
|----------------------------|----------------|
| Abandonment window         | Cart becomes `abandoned` after `ABANDONMENT_WINDOW_HOURS` (default 1 h) of inactivity and no linked order |
| Consent check              | Latest effective Consent for (customer, channel) must be `opt_in` |
| Follow-up messages         | After message `-01`, a cart may get `-02` (p=0.40) and `-03` (p=0.30), 24–48 h apart, rotating to another campaign/variant on the same channel |
| Frequency cap              | Max 2 non-suppressed sends per customer per channel inside a 7-day rolling window; a 3rd message is stored as `suppressed` / `frequency_cap` |
| Purchase suppression       | Follow-ups scheduled after the cart's order are stored as `suppressed` / `already_converted` |
| Attribution window         | Order attributed to a send if placed within 168 h (7 days) and send reached `opened`/`clicked` |
| Primary attribution        | Deterministic last-touch: most recent `opened`/`clicked` send of the same cart before the order (inside the window) receives `is_primary=true` |
| History preservation       | Consent changes and status transitions create new records; nothing is overwritten for consent |
| Derived values             | `Cart.total_amount` = Σ line totals; `CartLine.line_total` = qty × unit_price |

All parameters live in `src/config.py` and are documented.

---

## Required Edge Cases (Labelled in `ground_truth.csv`)

1. **message_sent_after_opt_out** – SendAttempt created despite active opt-out
2. **cart_abandoned_after_purchase** – Cart still marked abandoned after an Order exists
3. **attribution_double_counted** – Two primary attributions for the same Order
4. **cart_total_stale_after_quantity_update** – CartLine quantity changed but Cart.total_amount not recalculated

These records are **never** mixed into the normal feature tables as “correct” data; they are isolated in `ground_truth.csv` with expected decisions.

---

## Data Dictionary & Schema

Full field-level dictionary (types, allowed values, cardinality, validation rules) is in:

```
docs/data_dictionary.md
```

SQL schema reference:

```
docs/schema.sql
```

---

## Validation Performed by the Generator

- Primary-key uniqueness
- Foreign-key existence (Customer → Cart, Cart → Send, etc.)
- Enum value checks
- Date ordering (`created_at ≤ last_updated_at ≤ abandoned_at`)
- Arithmetic reconciliation of cart totals (except deliberately stale edge cases)
- Lifecycle consistency

Results are written to `manifest.json` and `validation_summary.txt`.

---

## Project Structure

```
abandoned-cart-recovery/
├── README.md
├── requirements.txt
├── docs/
│   ├── AI_USE.md
│   ├── data_dictionary.md
│   ├── prompt_history.md
│   └── schema.sql
├── src/
│   ├── __init__.py
│   ├── config.py          # Seed, volumes, business-rule constants
│   └── generator.py       # Full generation pipeline
├── data/                  # Output (git-ignored except demo / full CSVs)
└── tests/
    ├── test_reproducibility.py            # same seed → same checksums
    └── test_followups_and_attribution.py  # follow-ups, frequency cap, double attribution
```

---

## Design Decisions & Trade-offs

1. **Scale parameter** – Same code path produces a 1 000-cart starter set or the full 50 k-cart set. Reviewers can run the small version instantly.
2. **Fixed seed (20261022)** – Guarantees bit-for-bit reproducibility of IDs, timestamps and decisions.
3. **Event-sourced mindset** – Consent history is append-only.
4. **Explicit suppression reasons** – Every non-sent message records why (`opt_out`, `frequency_cap`, …).
5. **Ground-truth isolation** – Anomalies are never silently mixed into the main tables; they are labelled and kept separate so evaluation remains fair.
6. **No external personal data** – 100 % synthetic; Faker is used only for first/last names.

---

## How to Verify Core Functionality

```bash
# 1. Generate
python -m src.generator --scale 0.05 --out data/verify

# 2. Inspect a few records
head -5 data/verify/csv/carts.csv
head -5 data/verify/csv/send_attempts.csv
head -5 data/verify/csv/ground_truth.csv

# 3. Check validation
cat data/verify/validation_summary.txt

# 4. Confirm abandonment logic
python -c "
import pandas as pd
c = pd.read_csv('data/verify/csv/carts.csv')
print(c.status.value_counts())
print('Abandoned with timestamp:', c[c.status=='abandoned'].abandoned_at.notna().all())
"
```

---

## Coverage Status (all previously reported gaps fixed)

| Item | Status |
|------|--------|
| Recovered carts | Cart status set to `recovered` when a campaign-attributed order is placed |
| Late purchases | Orders outside the attribution window are generated and labelled `late_purchase` in ground_truth |
| Delivery / open / click events | Append-only `message_events` table (sent → delivered → opened → clicked / bounced); final status still on send_attempts |
| Opt-out anomaly count | Injection ensures the configured target (scaled) is met |
| Abandoned-cart volume | Generator forces exactly the target count |
| Customer-before-cart timestamps | Session/cart `created_at` is always ≥ customer `created_at` (validated) |
| SQL seed | 100-row sample per core table (full data in CSV/JSON) |
| All 4 required edge cases | Injected and isolated in ground_truth |
| Consent withdrawal, multi-device, frequency-cap conflicts | Present |
| Fixed seed + scale + reproducibility | Verified by tests |

What works and has been tested:

- Entities, stable IDs, fixed seed, scale parameter, validation report, separate ground-truth table
- Consent withdrawal, multiple devices, frequency-cap conflicts, recovered carts, late purchases
- All four required anomalies plus late-purchase labels
- Follow-up messages, last-touch attribution, suppression reasons, event history
- Reproducibility (same seed → identical checksums)
- Unit tests in `tests/` (`pytest -q`)

---

## Limitations & Next Steps

- Attribution currently uses the deterministic last-touch rule; multi-touch models (linear, time-decay) can be added later.
- SMS delivery receipts and real ESP webhooks are out of scope (synthetic only).
- Product catalogue is static; a full merchandising hierarchy is future work.
- Full 50 k run takes ~1–3 minutes on a modern laptop and produces ~80–120 MB of CSV.

---

## Prompt History / AI Use

All prompts submitted to AI coding assistants during development are recorded in:

```
docs/prompt_history.md
```

AI-use disclosure (where AI helped, where it was relied on heavily, and what was personally reviewed) lives in:

```
docs/AI_USE.md
```

---

## License & Provenance

Synthetic data generated solely for the YottaFlex AI recruitment exercise.  
No real customer data, no external proprietary datasets, no secrets.

---

**Ready for review.**  
I can walk through any decision, validation step or edge-case generation logic on request.
