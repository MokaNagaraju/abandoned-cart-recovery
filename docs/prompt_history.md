# Prompt History

All prompts I submitted to AI tools for this project, in order. Responses are omitted (optional per the FAQ).

---

## Tool: Grok (grok.x.ai), 28–29 Oct 2026

### Prompt 1
```
I need to build a synthetic data generator for an abandoned-cart recovery system.
Requirements include: Customer, Consent, Session, Cart, CartLine, Campaign,
MessageTemplate, SendAttempt, Order, Attribution entities.
50k carts, 20k abandoned, 10k sends.
Fixed seed, deterministic business rules for abandonment, consent, frequency caps,
attribution window. Labelled edge cases in a separate ground_truth file.
Please help me design a clean Python package structure and the data dictionary.
```

### Prompt 2
```
Write a complete Python generator class that:
- Uses a fixed seed (20261022)
- Supports a --scale parameter so the same code produces small demos and the full 50k dataset
- Generates parent entities first, then children
- Applies deterministic abandonment (1-hour window)
- Checks latest consent and frequency caps before creating SendAttempts
- Creates Orders and primary Attributions inside a 7-day window
- Injects the four required edge cases with ground_truth labels
- Exports CSV, JSON, a sample seed.sql, manifest with checksums, and validation report
```

### Prompt 3
```
Add validation for PK uniqueness, FK integrity, cart-total reconciliation
(excluding the deliberately stale edge cases), and date ordering.
Also refine the edge-case injection so that:
- message_sent_after_opt_out really has an active opt_out
- cart_abandoned_after_purchase has a real Order
- attribution_double_counted creates two is_primary=true rows
- cart_total_stale leaves the Cart.total_amount unchanged after a quantity update
```

### Prompt 4
```
Produce a professional README that explains how to run the generator on a laptop,
the business rules, the output layout, how to verify reproducibility,
and the design decisions. Also generate a full data dictionary markdown file.
```

### Prompt 5
```
Add follow-up messages (MSG-01, -02, -03), frequency-cap conflicts,
last-touch attribution, and fix the double-count attribution logic.
Also handle consent withdrawal, multiple devices, and make sure edge cases
are correctly labelled in ground_truth.csv.
```

### Prompt 6
```
The zip meets most of the problem statement, but several required items are still missing:
- Recovered carts: status is documented but never set
- Late purchases: they exist but aren’t labelled
- Delivery, open and click events: only the final status is stored, so history is overwritten
- Opt-out anomaly count: 14 generated, 25 configured
- Summary vs CSV: Summary says 20,000 abandoned, CSV shows about 19,250
- Carts created before their customer exists
- SQL seed: Only a 50-row sample per table
- Prompt history doesn’t yet include recent prompts

Please help update the docs and produce a final zip I can push to GitHub with known limitations documented.
```

### Prompt 7
```
can u add the prompts for me please like in a basic way can u doit and send the final zip file
where the conditions didnt meet also include and send me the file so i can push into github
and send the link do this help for me
```

---

## Tool: ChatGPT / Claude (as used in earlier sessions), ~28 Oct 2026

### Prompt A
```
Help me scaffold a Python package for synthetic abandoned-cart recovery data
with entities, fixed seed, scale parameter, and ground-truth anomalies.
```

### Prompt B
```
Review the generator logic for consent checks, frequency caps, and attribution
window. Suggest deterministic last-touch attribution and follow-up message scheduling.
```

---

*Prompts above are the ones I actually used. Some intermediate clarifying messages were omitted for brevity; the substance of every request is captured.*
