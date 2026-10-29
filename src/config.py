"""
Configuration and business rules for the Abandoned Cart Recovery synthetic data generator.
All tunable parameters live here so the same generator produces starter vs full datasets.
"""

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 20261022

# ---------------------------------------------------------------------------
# Scale (1.0 = full requested volumes)
# ---------------------------------------------------------------------------
# Full volumes requested by the problem statement:
#   50 000 carts, 20 000 abandoned, ~10 000 campaigns/sends
DEFAULT_SCALE = 1.0

# Base counts at scale=1.0
BASE_CUSTOMERS = 35_000
BASE_CARTS = 50_000
BASE_ABANDONED_TARGET = 20_000
BASE_SENDS = 10_000
BASE_CAMPAIGNS = 40          # few campaigns, many sends
BASE_PRODUCTS = 200

# ---------------------------------------------------------------------------
# Business Rules (documented & deterministic)
# ---------------------------------------------------------------------------
ABANDONMENT_WINDOW_HOURS = 1          # inactivity after last cart update
ATTRIBUTION_WINDOW_HOURS = 168        # 7 days
FREQUENCY_WINDOW_DAYS = 7
MAX_SENDS_PER_CUSTOMER_PER_WINDOW = 2   # per customer, per channel, per rolling FREQUENCY_WINDOW_DAYS

# Follow-up messages (MSG-<cart>-01, -02, -03)
MAX_MESSAGES_PER_CART = 3
P_FOLLOWUP_1 = 0.40                   # chance a cart gets a 2nd message after the 1st
P_FOLLOWUP_2 = 0.30                   # chance a cart gets a 3rd message after the 2nd
FOLLOWUP_GAP_HOURS = (24, 48)         # gap between consecutive messages for a cart

# Minimum time between cart creation and possible abandonment evaluation
MIN_CART_AGE_HOURS = 2

# Probability knobs (still deterministic via seeded RNG)
P_OPT_OUT = 0.08
P_CONSENT_WITHDRAWAL = 0.04
P_MULTI_DEVICE = 0.15
P_RECOVERY_AFTER_SEND = 0.22
P_ORGANIC_ORDER = 0.05
P_CLICK = 0.35
P_OPEN = 0.55

# Time range for synthetic data
START_DATE = datetime(2026, 8, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 10, 25, tzinfo=timezone.utc)

# Currencies & countries
CURRENCIES = ["USD", "INR", "EUR", "GBP"]
COUNTRY_CURRENCY = {
    "US": "USD",
    "IN": "INR",
    "GB": "GBP",
    "DE": "EUR",
    "FR": "EUR",
    "CA": "USD",
    "AU": "USD",
}
COUNTRIES = list(COUNTRY_CURRENCY.keys())

CHANNELS = ["email", "sms"]
CAMPAIGN_VARIANTS = ["A", "B", "C"]

# Edge-case injection counts (absolute, independent of scale for visibility)
N_EDGE_MESSAGE_AFTER_OPTOUT = 25
N_EDGE_ABANDONED_AFTER_PURCHASE = 20
N_EDGE_ATTRIBUTION_DOUBLE = 15
N_EDGE_STALE_CART_TOTAL = 30
