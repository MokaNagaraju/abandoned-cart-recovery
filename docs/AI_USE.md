# AI Use Disclosure

**Tools used:** Grok, ChatGPT, Claude.

## Where AI accelerated my work
- Project scaffolding, package layout, and initial documentation drafts
- Boilerplate for CSV/JSON/SQL export, checksums, and CLI argument parsing
- First draft of the data dictionary and README structure

## Where I relied heavily on AI
- Follow-up message scheduling logic (MSG-01 / -02 / -03)
- Frequency-cap conflict handling and suppression reasons
- Last-touch attribution loop and double-attribution edge-case injection
- Validation checks (PK/FK, cart-total reconciliation, date ordering)
- Ground-truth anomaly construction for the four required edge cases

## What I personally reviewed, changed or validated
- Ran the generator at demo scale (`--scale 0.02`) and inspected the CSVs
- Checked row counts, anomaly counts, validation output and test results
- Ran the generator twice with the same seed and compared checksums in `manifest.json`
- Adjusted edge-case injection counts and suppression logic after inspecting output
- Verified that `ground_truth.csv` isolates anomalies and does not pollute main tables
- Confirmed reproducibility tests pass (`pytest -q`)

## Limitations of my prompt record
- Some intermediate clarifying messages and tool-specific UI chats were copied by hand;
  a small number of very short follow-ups may be missing, but every substantive request
  used for design or code is listed in `docs/prompt_history.md`.

## Data & safety
- All data is 100 % synthetic (Faker names, `example.com` emails, random phones).
- The repository contains no secrets, credentials, API keys or proprietary code.
- No configuration requires secrets; all settings live in `src/config.py`.
