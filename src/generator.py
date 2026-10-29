#!/usr/bin/env python3
"""
Abandoned Cart Recovery – Synthetic Data Generator
==================================================
Produces a fully consistent, reproducible multi-entity dataset that implements:

  • Master data generation (Customer, Consent, Session, Cart, CartLine …)
  • Deterministic business rules (abandonment windows, consent, frequency caps,
    campaign scheduling, attribution)
  • Explicit event history (no overwrites)
  • Labelled edge cases + separate ground_truth
  • Validation, reproducibility checks, CSV / JSON / SQL export

Usage
-----
  python -m src.generator --scale 0.02 --out data/demo
  python -m src.generator --scale 1.0  --out data/full   # full 50k carts

All randomness is controlled by the fixed seed in config.SEED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from faker import Faker
from tqdm import tqdm

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config as cfg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def pad_id(prefix: str, n: int, width: int = 6) -> str:
    return f"{prefix}{n:0{width}d}"


def cart_id(n: int) -> str:
    return f"CART-2026-{n:06d}"


def campaign_id(n: int) -> str:
    return f"CMP-2026-{n:06d}"


def send_id(n: int) -> str:
    return f"SEND-2026-{n:06d}"


def order_id(n: int) -> str:
    return f"ORD-2026-{n:06d}"


def checksum_df(df: pd.DataFrame) -> str:
    """Stable content hash for reproducibility checks."""
    if df.empty:
        return "empty"
    # Sort by first column if it looks like an ID
    col0 = df.columns[0]
    sorted_df = df.sort_values(col0).reset_index(drop=True)
    csv_bytes = sorted_df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Main Generator Class
# ---------------------------------------------------------------------------

class AbandonedCartGenerator:
    def __init__(self, scale: float = 1.0, seed: int = cfg.SEED):
        self.scale = max(0.001, float(scale))
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.fake = Faker()
        Faker.seed(seed)

        # Scaled volumes
        self.n_customers = max(100, int(cfg.BASE_CUSTOMERS * self.scale))
        self.n_carts = max(200, int(cfg.BASE_CARTS * self.scale))
        self.n_abandoned_target = max(50, int(cfg.BASE_ABANDONED_TARGET * self.scale))
        self.n_sends = max(100, int(cfg.BASE_SENDS * self.scale))
        self.n_campaigns = max(5, int(cfg.BASE_CAMPAIGNS * self.scale))
        self.n_products = max(20, int(cfg.BASE_PRODUCTS * self.scale))

        # Edge-case counts (keep visible even at small scale)
        self.n_edge_optout = max(3, int(cfg.N_EDGE_MESSAGE_AFTER_OPTOUT * min(1.0, self.scale * 5)))
        self.n_edge_abandon_after = max(2, int(cfg.N_EDGE_ABANDONED_AFTER_PURCHASE * min(1.0, self.scale * 5)))
        self.n_edge_double_attr = max(2, int(cfg.N_EDGE_ATTRIBUTION_DOUBLE * min(1.0, self.scale * 5)))
        self.n_edge_stale = max(3, int(cfg.N_EDGE_STALE_CART_TOTAL * min(1.0, self.scale * 5)))

        # Storage
        self.customers: List[Dict] = []
        self.consents: List[Dict] = []
        self.sessions: List[Dict] = []
        self.carts: List[Dict] = []
        self.cart_lines: List[Dict] = []
        self.campaigns: List[Dict] = []
        self.templates: List[Dict] = []
        self.sends: List[Dict] = []
        self.events: List[Dict] = []          # delivery / open / click history (append-only)
        self.orders: List[Dict] = []
        self.attributions: List[Dict] = []
        self.ground_truth: List[Dict] = []

        # Indexes for fast lookup
        self.customer_by_id: Dict[str, Dict] = {}
        self.consent_by_customer: Dict[str, List[Dict]] = defaultdict(list)
        self.cart_by_id: Dict[str, Dict] = {}
        self.sends_by_customer: Dict[str, List[Dict]] = defaultdict(list)

        # Counters
        self._cus_seq = 0
        self._con_seq = 0
        self._ses_seq = 0
        self._cln_seq = 0
        self._tpl_seq = 0
        self._att_seq = 0
        self._dev_seq = 0
        self._evt_seq = 0

        # Product catalogue (shared)
        self.products: List[Dict] = []

        self.stats: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------
    def random_dt(self, start: datetime = None, end: datetime = None) -> datetime:
        start = start or cfg.START_DATE
        end = end or cfg.END_DATE
        delta = (end - start).total_seconds()
        offset = self.rng.uniform(0, delta)
        return start + timedelta(seconds=offset)

    def later(self, base: datetime, min_hours: float = 0.1, max_hours: float = 48) -> datetime:
        h = self.rng.uniform(min_hours, max_hours)
        return base + timedelta(hours=h)

    # ------------------------------------------------------------------
    # 1. Products (master)
    # ------------------------------------------------------------------
    def generate_products(self):
        names = [
            "Wireless Earbuds", "Organic Cotton Tee", "Smart Watch", "Yoga Mat",
            "Stainless Bottle", "Bluetooth Speaker", "Running Shoes", "Desk Lamp",
            "Protein Powder", "Leather Wallet", "Noise Cancelling Headphones",
            "Ceramic Mug Set", "Fitness Tracker", "Backpack", "Sunglasses",
            "Phone Case", "Portable Charger", "Kitchen Knife Set", "Scented Candle",
            "Gaming Mouse"
        ]
        for i in range(1, self.n_products + 1):
            name = names[(i - 1) % len(names)] + f" {i}"
            self.products.append({
                "product_id": f"PRD-{i:04d}",
                "product_name": name,
                "base_price": round(float(self.rng.uniform(9.99, 249.99)), 2),
            })

    # ------------------------------------------------------------------
    # 2. Customers + Consent
    # ------------------------------------------------------------------
    def generate_customers_and_consents(self):
        print(f"Generating {self.n_customers:,} customers + consents …")
        for i in range(1, self.n_customers + 1):
            self._cus_seq = i
            cid = pad_id("CUS-", i)
            country = self.rng.choice(cfg.COUNTRIES)
            created = self.random_dt(cfg.START_DATE, cfg.START_DATE + timedelta(days=40))

            cust = {
                "customer_id": cid,
                "email": f"user{i:05d}@example.com",
                "phone": f"+1{self.rng.integers(2000000000, 9999999999)}",
                "first_name": self.fake.first_name(),
                "last_name": self.fake.last_name(),
                "country_code": country,
                "created_at": iso(created),
                "is_active": True,
            }
            self.customers.append(cust)
            self.customer_by_id[cid] = cust

            # Initial consent for both channels (most opt-in; some start opted-out)
            for ch in cfg.CHANNELS:
                self._con_seq += 1
                initial_status = "opt_out" if self.rng.random() < cfg.P_OPT_OUT else "opt_in"
                con = {
                    "consent_id": pad_id("CON-", self._con_seq),
                    "customer_id": cid,
                    "channel": ch,
                    "status": initial_status,
                    "effective_from": iso(created),
                    "effective_to": None,
                    "source": "registration",
                }
                self.consents.append(con)
                self.consent_by_customer[cid].append(con)

            # Some customers who started opt-in later withdraw consent
            if self.rng.random() < cfg.P_CONSENT_WITHDRAWAL:
                ch = self.rng.choice(cfg.CHANNELS)
                # only withdraw if currently opt_in
                current = [c for c in self.consent_by_customer[cid]
                           if c["channel"] == ch and c["effective_to"] is None]
                if current and current[0]["status"] == "opt_in":
                    withdraw_at = self.later(created, 24, 720)
                    for c in current:
                        c["effective_to"] = iso(withdraw_at)
                    self._con_seq += 1
                    con2 = {
                        "consent_id": pad_id("CON-", self._con_seq),
                        "customer_id": cid,
                        "channel": ch,
                        "status": "opt_out",
                        "effective_from": iso(withdraw_at),
                        "effective_to": None,
                        "source": "preference_center",
                    }
                    self.consents.append(con2)
                    self.consent_by_customer[cid].append(con2)

    def latest_consent(self, customer_id: str, channel: str, as_of: datetime) -> Optional[Dict]:
        candidates = [
            c for c in self.consent_by_customer.get(customer_id, [])
            if c["channel"] == channel
            and utc(datetime.fromisoformat(c["effective_from"].replace("Z", "+00:00"))) <= as_of
            and (c["effective_to"] is None or
                 utc(datetime.fromisoformat(c["effective_to"].replace("Z", "+00:00"))) > as_of)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["effective_from"])

    # ------------------------------------------------------------------
    # 3. Sessions + Carts + CartLines
    # ------------------------------------------------------------------
    def generate_sessions_carts_lines(self):
        print(f"Generating sessions, {self.n_carts:,} carts and cart lines …")
        product_ids = [p["product_id"] for p in self.products]
        product_map = {p["product_id"]: p for p in self.products}

        # Pre-allocate some multi-device customers
        multi_device_customers = set(
            self.rng.choice(
                [c["customer_id"] for c in self.customers],
                size=int(self.n_customers * cfg.P_MULTI_DEVICE),
                replace=False,
            )
        )

        for i in tqdm(range(1, self.n_carts + 1), desc="Carts"):
            cust = self.customers[(i - 1) % self.n_customers]
            cid = cust["customer_id"]
            cust_created = datetime.fromisoformat(cust["created_at"].replace("Z", "+00:00"))

            # Session — always after the customer was created
            self._ses_seq += 1
            sid = pad_id("SES-", self._ses_seq)
            self._dev_seq += 1
            device = f"DEV-{self._dev_seq:08d}"
            if cid in multi_device_customers and self.rng.random() < 0.4:
                # reuse an earlier device sometimes
                device = f"DEV-{(self._dev_seq % 50) + 1:08d}"

            # Session start must be >= customer.created_at
            session_floor = max(cust_created, cfg.START_DATE)
            if session_floor >= cfg.END_DATE - timedelta(hours=2):
                session_floor = cfg.START_DATE
            started = self.random_dt(session_floor, cfg.END_DATE - timedelta(hours=1))
            if started < cust_created:
                started = cust_created + timedelta(minutes=int(self.rng.integers(5, 120)))
            ended = self.later(started, 0.05, 3)
            if ended > cfg.END_DATE:
                ended = cfg.END_DATE
            session = {
                "session_id": sid,
                "customer_id": cid,
                "device_id": device,
                "started_at": iso(started),
                "ended_at": iso(ended),
                "user_agent": self.rng.choice([
                    "Mozilla/5.0 (iPhone)", "Mozilla/5.0 (Windows NT 10.0)",
                    "Mozilla/5.0 (Macintosh)", "Mozilla/5.0 (Android)"
                ]),
            }
            self.sessions.append(session)

            # Cart
            created = started + timedelta(minutes=int(self.rng.integers(1, 20)))
            n_lines = int(self.rng.integers(1, 6))
            lines = []
            total = 0.0
            for _ in range(n_lines):
                self._cln_seq += 1
                pid = self.rng.choice(product_ids)
                prod = product_map[pid]
                qty = int(self.rng.integers(1, 4))
                unit = prod["base_price"]
                # small price variation
                unit = round(unit * float(self.rng.uniform(0.9, 1.1)), 2)
                line_total = round(qty * unit, 2)
                total += line_total
                updated = created + timedelta(minutes=int(self.rng.integers(0, 30)))
                lines.append({
                    "cart_line_id": pad_id("CLN-", self._cln_seq),
                    "cart_id": cart_id(i),
                    "product_id": pid,
                    "product_name": prod["product_name"],
                    "quantity": qty,
                    "unit_price": unit,
                    "line_total": line_total,
                    "updated_at": iso(updated),
                })

            last_updated = max(
                datetime.fromisoformat(l["updated_at"].replace("Z", "+00:00")) for l in lines
            )
            currency = cfg.COUNTRY_CURRENCY.get(cust["country_code"], "USD")

            cart = {
                "cart_id": cart_id(i),
                "customer_id": cid,
                "session_id": sid,
                "status": "active",          # will be updated later
                "created_at": iso(created),
                "last_updated_at": iso(last_updated),
                "abandoned_at": None,
                "currency": currency,
                "total_amount": round(total, 2),
            }
            self.carts.append(cart)
            self.cart_by_id[cart["cart_id"]] = cart
            self.cart_lines.extend(lines)

        # ------------------------------------------------------------------
        # Apply abandonment logic (deterministic) — hit the target count
        # ------------------------------------------------------------------
        print("Applying abandonment windows …")
        # Prefer older carts so abandon_at stays inside the data window
        candidates = sorted(
            self.carts,
            key=lambda c: c["last_updated_at"],
        )
        abandoned_count = 0
        for cart in candidates:
            if abandoned_count >= self.n_abandoned_target:
                break
            last = datetime.fromisoformat(cart["last_updated_at"].replace("Z", "+00:00"))
            age_hours = (cfg.END_DATE - last).total_seconds() / 3600
            if age_hours <= cfg.ABANDONMENT_WINDOW_HOURS:
                # Pull last_updated earlier so the cart is eligible
                last = cfg.END_DATE - timedelta(hours=cfg.ABANDONMENT_WINDOW_HOURS + self.rng.uniform(2, 48))
                created = datetime.fromisoformat(cart["created_at"].replace("Z", "+00:00"))
                if last < created:
                    last = created + timedelta(minutes=30)
                cart["last_updated_at"] = iso(last)
            abandon_at = last + timedelta(hours=cfg.ABANDONMENT_WINDOW_HOURS + self.rng.uniform(0.1, 12))
            if abandon_at > cfg.END_DATE:
                abandon_at = cfg.END_DATE - timedelta(minutes=30)
            if abandon_at <= last:
                abandon_at = last + timedelta(hours=cfg.ABANDONMENT_WINDOW_HOURS)
            cart["status"] = "abandoned"
            cart["abandoned_at"] = iso(abandon_at)
            abandoned_count += 1

        self.stats["abandoned_carts"] = abandoned_count
        print(f"  → {abandoned_count:,} carts marked abandoned (target {self.n_abandoned_target:,})")

    # ------------------------------------------------------------------
    # 4. Campaigns + Templates
    # ------------------------------------------------------------------
    def generate_campaigns_and_templates(self):
        print(f"Generating {self.n_campaigns} campaigns + templates …")
        for i in range(1, self.n_campaigns + 1):
            ch = self.rng.choice(cfg.CHANNELS)
            variant = self.rng.choice(cfg.CAMPAIGN_VARIANTS)
            start = self.random_dt(cfg.START_DATE + timedelta(days=10), cfg.END_DATE - timedelta(days=5))
            end = start + timedelta(days=int(self.rng.integers(7, 30)))
            camp = {
                "campaign_id": campaign_id(i),
                "name": f"Abandoned Cart Recovery {variant} – {ch.upper()} #{i}",
                "channel": ch,
                "variant": variant,
                "start_at": iso(start),
                "end_at": iso(end),
                "status": "completed" if end < cfg.END_DATE else "active",
            }
            self.campaigns.append(camp)

            self._tpl_seq += 1
            tpl = {
                "template_id": pad_id("TPL-", self._tpl_seq),
                "campaign_id": camp["campaign_id"],
                "channel": ch,
                "subject": f"You left something behind – {variant}" if ch == "email" else None,
                "body": f"Hi {{{{first_name}}}}, your cart is waiting. Complete your purchase now! (variant {variant})",
                "variant": variant,
            }
            self.templates.append(tpl)

    # ------------------------------------------------------------------
    # 5. SendAttempts (with consent + frequency rules + follow-ups)
    # ------------------------------------------------------------------
    def _emit_event(self, send_id_str: str, event_type: str, at: datetime):
        """Append-only message event (delivery / open / click / bounce)."""
        self._evt_seq += 1
        self.events.append({
            "event_id": pad_id("EVT-", self._evt_seq),
            "send_id": send_id_str,
            "event_type": event_type,   # sent | delivered | opened | clicked | bounced
            "event_at": iso(at),
        })

    def _evaluate_send(self, cust_id: str, channel: str, scheduled: datetime):
        """Return (status, suppression_reason) for a message scheduled at `scheduled`.

        Rules (in priority order):
          1. latest effective consent for (customer, channel) must be opt_in
          2. at most MAX_SENDS_PER_CUSTOMER_PER_WINDOW non-suppressed sends for the same
             customer + channel in the FREQUENCY_WINDOW_DAYS *before* `scheduled`
        """
        consent = self.latest_consent(cust_id, channel, scheduled)
        if consent is None or consent["status"] == "opt_out":
            return "suppressed", "opt_out"
        window_start = scheduled - timedelta(days=cfg.FREQUENCY_WINDOW_DAYS)
        recent = [
            s for s in self.sends_by_customer[cust_id]
            if s["channel"] == channel
            and s["status"] != "suppressed"
            and window_start < datetime.fromisoformat(s["scheduled_at"].replace("Z", "+00:00")) <= scheduled
        ]
        if len(recent) >= cfg.MAX_SENDS_PER_CUSTOMER_PER_WINDOW:
            return "suppressed", "frequency_cap"
        return "scheduled", None

    def generate_sends(self):
        print(f"Generating up to {self.n_sends:,} send attempts (with follow-ups) …")
        abandoned = [c for c in self.carts if c["status"] == "abandoned"]
        self.rng.shuffle(abandoned)

        template_by_campaign = {t["campaign_id"]: t for t in self.templates}
        campaigns_by_channel: Dict[str, List[Dict]] = defaultdict(list)
        for c in self.campaigns:
            campaigns_by_channel[c["channel"]].append(c)

        send_counter = 0
        for cart in tqdm(abandoned, desc="Sends"):
            if send_counter >= self.n_sends:
                break

            cust_id = cart["customer_id"]
            abandon_at = datetime.fromisoformat(cart["abandoned_at"].replace("Z", "+00:00"))
            camp = self.rng.choice(self.campaigns)
            channel = camp["channel"]
            scheduled = abandon_at + timedelta(hours=self.rng.uniform(0.5, 24))
            if scheduled > cfg.END_DATE:
                continue

            seq = 1
            while True:
                tpl = template_by_campaign[camp["campaign_id"]]
                status, suppression_reason = self._evaluate_send(cust_id, channel, scheduled)

                send_counter += 1
                sid = send_id(send_counter)
                sent_at = None
                if status != "suppressed":
                    sent_at = scheduled + timedelta(minutes=int(self.rng.integers(1, 30)))
                    # Append-only event history: sent → delivered → opened → clicked (or bounce)
                    self._emit_event(sid, "sent", sent_at)
                    r = self.rng.random()
                    if r < 0.05:
                        status = "bounced"
                        bounce_at = sent_at + timedelta(minutes=int(self.rng.integers(1, 15)))
                        self._emit_event(sid, "bounced", bounce_at)
                    else:
                        delivered_at = sent_at + timedelta(minutes=int(self.rng.integers(1, 10)))
                        self._emit_event(sid, "delivered", delivered_at)
                        status = "delivered"
                        if self.rng.random() < cfg.P_OPEN:
                            open_at = delivered_at + timedelta(minutes=int(self.rng.integers(1, 120)))
                            self._emit_event(sid, "opened", open_at)
                            status = "opened"
                            if self.rng.random() < cfg.P_CLICK:
                                click_at = open_at + timedelta(minutes=int(self.rng.integers(1, 60)))
                                self._emit_event(sid, "clicked", click_at)
                                status = "clicked"

                rec = {
                    "send_id": sid,
                    "cart_id": cart["cart_id"],
                    "campaign_id": camp["campaign_id"],
                    "template_id": tpl["template_id"],
                    "message_id": f"MSG-{cart['cart_id']}-{seq:02d}",
                    "customer_id": cust_id,
                    "channel": channel,
                    "scheduled_at": iso(scheduled),
                    "sent_at": iso(sent_at) if sent_at else None,
                    "status": status,          # final status (events table holds the full history)
                    "suppression_reason": suppression_reason,
                }
                self.sends.append(rec)
                self.sends_by_customer[cust_id].append(rec)

                # ---- decide whether a follow-up message is scheduled ----
                if suppression_reason == "opt_out":
                    break                      # no point following up an opted-out contact
                if seq >= cfg.MAX_MESSAGES_PER_CART or send_counter >= self.n_sends:
                    break
                p_next = cfg.P_FOLLOWUP_1 if seq == 1 else cfg.P_FOLLOWUP_2
                if self.rng.random() >= p_next:
                    break
                scheduled = scheduled + timedelta(hours=self.rng.uniform(*cfg.FOLLOWUP_GAP_HOURS))
                if scheduled > cfg.END_DATE:
                    break
                seq += 1
                # follow-up rotates to a different campaign/variant on the same channel when possible
                others = [c for c in campaigns_by_channel[channel] if c["campaign_id"] != camp["campaign_id"]]
                if others:
                    camp = others[int(self.rng.integers(0, len(others)))]

        # Post-pass: enforce frequency cap across all customers (generation order can
        # interleave carts so a later-scheduled send was created before an earlier one).
        by_cc: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        for s in self.sends:
            if s["status"] != "suppressed":
                by_cc[(s["customer_id"], s["channel"])].append(s)
        win = timedelta(days=cfg.FREQUENCY_WINDOW_DAYS)
        for key, lst in by_cc.items():
            lst.sort(key=lambda x: x["scheduled_at"])
            kept: List[datetime] = []
            for s in lst:
                t = datetime.fromisoformat(s["scheduled_at"].replace("Z", "+00:00"))
                kept = [u for u in kept if t - u < win]
                if len(kept) >= cfg.MAX_SENDS_PER_CUSTOMER_PER_WINDOW:
                    s["status"] = "suppressed"
                    s["sent_at"] = None
                    s["suppression_reason"] = "frequency_cap"
                    # Drop any events that were emitted for this send
                    self.events = [e for e in self.events if e["send_id"] != s["send_id"]]
                else:
                    kept.append(t)

        self.stats["sends_generated"] = len(self.sends)
        n_follow = sum(1 for s in self.sends if not s["message_id"].endswith("-01"))
        n_cap = sum(1 for s in self.sends if s["suppression_reason"] == "frequency_cap")
        print(f"  → {len(self.sends):,} send attempts created ({n_follow:,} follow-ups, {n_cap:,} blocked by frequency cap)")

    # ------------------------------------------------------------------
    # 6. Orders + Attribution
    # ------------------------------------------------------------------
    def generate_orders_and_attribution(self):
        print("Generating orders and attribution …")
        # Recovered / converted carts after successful sends
        clicked_or_opened = [
            s for s in self.sends
            if s["status"] in ("opened", "clicked") and s["sent_at"]
        ]
        self.rng.shuffle(clicked_or_opened)

        order_counter = 0
        attributed = 0

        # cart -> its baseline sends (before any anomaly injection)
        self.sends_by_cart_baseline: Dict[str, List[Dict]] = defaultdict(list)
        for s in self.sends:
            self.sends_by_cart_baseline[s["cart_id"]].append(s)

        for send in clicked_or_opened:
            if self.rng.random() > cfg.P_RECOVERY_AFTER_SEND:
                continue
            cart = self.cart_by_id[send["cart_id"]]
            if cart["status"] != "abandoned":
                continue

            sent_at = datetime.fromisoformat(send["sent_at"].replace("Z", "+00:00"))
            order_at = sent_at + timedelta(hours=self.rng.uniform(1, cfg.ATTRIBUTION_WINDOW_HOURS * 0.8))
            if order_at > cfg.END_DATE:
                continue

            order_counter += 1
            oid = order_id(order_counter)
            amount = cart["total_amount"]
            # small chance of different amount (partial recovery)
            if self.rng.random() < 0.15:
                amount = round(amount * float(self.rng.uniform(0.6, 1.0)), 2)

            order = {
                "order_id": oid,
                "customer_id": cart["customer_id"],
                "cart_id": cart["cart_id"],
                "order_at": iso(order_at),
                "total_amount": amount,
                "currency": cart["currency"],
                "status": "paid",
            }
            self.orders.append(order)

            # Mark cart recovered (campaign-driven recovery)
            cart["status"] = "recovered"

            # Follow-ups scheduled after the purchase are not sent (explicit suppression).
            for later in self.sends_by_cart_baseline[cart["cart_id"]]:
                if (later["status"] != "suppressed"
                        and datetime.fromisoformat(later["scheduled_at"].replace("Z", "+00:00")) >= order_at):
                    later["status"] = "suppressed"
                    later["sent_at"] = None
                    later["suppression_reason"] = "already_converted"

            # Primary attribution = deterministic last-touch: the most recent qualifying send
            # (opened/clicked) for this cart that precedes the order inside the attribution window.
            window = timedelta(hours=cfg.ATTRIBUTION_WINDOW_HOURS)
            touches = [
                s for s in self.sends_by_cart_baseline[cart["cart_id"]]
                if s["status"] in ("opened", "clicked") and s["sent_at"]
                and 0 <= (order_at - datetime.fromisoformat(s["sent_at"].replace("Z", "+00:00"))).total_seconds()
                <= window.total_seconds()
            ]
            send = max(touches, key=lambda s: (s["sent_at"], s["send_id"]))

            self._att_seq += 1
            att = {
                "attribution_id": pad_id("ATT-", self._att_seq),
                "order_id": oid,
                "send_id": send["send_id"],
                "campaign_id": send["campaign_id"],
                "attributed_amount": amount,
                "attribution_window_hours": cfg.ATTRIBUTION_WINDOW_HOURS,
                "is_primary": True,
            }
            self.attributions.append(att)
            attributed += 1

        # A few organic orders (no cart / no attribution)
        for _ in range(int(self.n_customers * cfg.P_ORGANIC_ORDER * 0.3)):
            cust = self.rng.choice(self.customers)
            order_counter += 1
            self.orders.append({
                "order_id": order_id(order_counter),
                "customer_id": cust["customer_id"],
                "cart_id": None,
                "order_at": iso(self.random_dt()),
                "total_amount": round(float(self.rng.uniform(20, 300)), 2),
                "currency": cfg.COUNTRY_CURRENCY.get(cust["country_code"], "USD"),
                "status": "paid",
            })

        # Late purchases: order placed *after* the attribution window for an abandoned cart
        # that had at least one opened/clicked send. No attribution is created; labelled in ground_truth.
        still_abandoned = [c for c in self.carts if c["status"] == "abandoned"]
        self.rng.shuffle(still_abandoned)
        n_late = max(5, int(30 * min(1.0, self.scale * 5)))
        late_count = 0
        for cart in still_abandoned:
            if late_count >= n_late:
                break
            touches = [
                s for s in self.sends_by_cart_baseline.get(cart["cart_id"], [])
                if s["status"] in ("opened", "clicked") and s["sent_at"]
            ]
            if not touches:
                continue
            last_touch = max(
                datetime.fromisoformat(s["sent_at"].replace("Z", "+00:00")) for s in touches
            )
            # Place order strictly outside the attribution window
            order_at = last_touch + timedelta(
                hours=cfg.ATTRIBUTION_WINDOW_HOURS + self.rng.uniform(12, 72)
            )
            if order_at > cfg.END_DATE:
                continue
            order_counter += 1
            oid = order_id(order_counter)
            amount = cart["total_amount"]
            self.orders.append({
                "order_id": oid,
                "customer_id": cart["customer_id"],
                "cart_id": cart["cart_id"],
                "order_at": iso(order_at),
                "total_amount": amount,
                "currency": cart["currency"],
                "status": "paid",
            })
            # Cart remains abandoned (late purchase is outside recovery attribution)
            # Label in ground_truth so evaluators can see it
            self.ground_truth.append({
                "entity_type": "Order",
                "entity_id": oid,
                "issue_type": "late_purchase",
                "description": (
                    f"Order {oid} for cart {cart['cart_id']} placed "
                    f"{cfg.ATTRIBUTION_WINDOW_HOURS}+ hours after last qualifying send — outside attribution window"
                ),
                "expected_decision": "no attribution row; cart stays abandoned (or recovered without campaign credit)",
            })
            late_count += 1
        self.stats["late_purchases"] = late_count

        self.stats["orders"] = len(self.orders)
        self.stats["attributions"] = len(self.attributions)
        print(f"  → {len(self.orders):,} orders, {len(self.attributions):,} attributions, {late_count} late purchases")

    # ------------------------------------------------------------------
    # 7. Inject labelled edge cases
    # ------------------------------------------------------------------
    def inject_edge_cases(self):
        print("Injecting labelled edge cases …")

        # --- 1. Message sent after opt-out ---
        # Deliberately create sends that ignore active opt-out consent
        opt_out_customers = []
        for cid, cons_list in self.consent_by_customer.items():
            for c in cons_list:
                if c["status"] == "opt_out" and c["effective_to"] is None:
                    opt_out_customers.append((cid, c["channel"]))
                    break
        self.rng.shuffle(opt_out_customers)

        # Ensure we have enough (customer, channel) pairs with an abandoned cart
        eligible = []
        for cid, channel in opt_out_customers:
            cart = next(
                (c for c in self.carts if c["customer_id"] == cid and c["status"] == "abandoned"),
                None,
            )
            if cart:
                eligible.append((cid, channel, cart))
        # If still short, force opt-out on additional abandoned-cart customers
        if len(eligible) < self.n_edge_optout:
            extra_carts = [c for c in self.carts if c["status"] == "abandoned"
                           and c["customer_id"] not in {e[0] for e in eligible}]
            self.rng.shuffle(extra_carts)
            for cart in extra_carts:
                if len(eligible) >= self.n_edge_optout:
                    break
                cid = cart["customer_id"]
                channel = self.rng.choice(cfg.CHANNELS)
                # Close any active opt_in and add opt_out
                for c in self.consent_by_customer[cid]:
                    if c["channel"] == channel and c["effective_to"] is None:
                        c["effective_to"] = cart["abandoned_at"]
                self._con_seq += 1
                con = {
                    "consent_id": pad_id("CON-", self._con_seq),
                    "customer_id": cid,
                    "channel": channel,
                    "status": "opt_out",
                    "effective_from": cart["abandoned_at"],
                    "effective_to": None,
                    "source": "preference_center",
                }
                self.consents.append(con)
                self.consent_by_customer[cid].append(con)
                eligible.append((cid, channel, cart))

        optout_injected = 0
        for cid, channel, cart in eligible[: self.n_edge_optout]:
            camp = next((c for c in self.campaigns if c["channel"] == channel), self.campaigns[0])
            tpl = next(t for t in self.templates if t["campaign_id"] == camp["campaign_id"])
            abandon_at = datetime.fromisoformat(cart["abandoned_at"].replace("Z", "+00:00"))
            scheduled = abandon_at + timedelta(hours=2)
            sid = send_id(len(self.sends) + 1)
            next_seq = len(self.sends_by_cart_baseline.get(cart["cart_id"], [])) + 1
            # DELIBERATELY send despite opt-out
            rec = {
                "send_id": sid,
                "cart_id": cart["cart_id"],
                "campaign_id": camp["campaign_id"],
                "template_id": tpl["template_id"],
                "message_id": f"MSG-{cart['cart_id']}-{next_seq:02d}",
                "customer_id": cid,
                "channel": channel,
                "scheduled_at": iso(scheduled),
                "sent_at": iso(scheduled + timedelta(minutes=5)),
                "status": "sent",               # anomaly
                "suppression_reason": None,     # should have been opt_out
            }
            self.sends.append(rec)
            optout_injected += 1
            self.ground_truth.append({
                "entity_type": "SendAttempt",
                "entity_id": sid,
                "issue_type": "message_sent_after_opt_out",
                "description": f"Send {sid} was emitted even though customer {cid} had active opt_out for {channel}",
                "expected_decision": "status=suppressed, suppression_reason=opt_out",
            })
        self.stats["optout_anomalies"] = optout_injected

        # --- 2. Cart considered abandoned after purchase ---
        # Create a cart that has an order but is still marked abandoned
        for k in range(self.n_edge_abandon_after):
            # Pick a recovered cart and force its status back to abandoned
            recovered = [c for c in self.carts if c["status"] == "recovered"]
            if not recovered:
                break
            cart = recovered[k % len(recovered)]
            # Find its order
            order = next((o for o in self.orders if o["cart_id"] == cart["cart_id"]), None)
            if not order:
                continue
            cart["status"] = "abandoned"   # anomaly: should be recovered
            # Keep abandoned_at
            self.ground_truth.append({
                "entity_type": "Cart",
                "entity_id": cart["cart_id"],
                "issue_type": "cart_abandoned_after_purchase",
                "description": f"Cart {cart['cart_id']} is marked abandoned even though order {order['order_id']} exists",
                "expected_decision": "status=recovered (order already placed via campaign)",
            })

        # --- 3. Attribution double-counted across campaigns ---
        # Keep scanning ALL primary attributions until n_edge_double_attr doubles exist.
        # A second primary is only created from another *qualifying* send (opened/clicked, sent
        # before the order and inside the attribution window) of the same cart that belongs to a
        # DIFFERENT campaign - i.e. the same order is credited twice across campaigns.
        primary_atts = [a for a in self.attributions if a["is_primary"]]
        send_by_id = {s["send_id"]: s for s in self.sends}
        order_by_id = {o["order_id"]: o for o in self.orders}
        window_s = cfg.ATTRIBUTION_WINDOW_HOURS * 3600
        doubles = 0
        for att in primary_atts:
            if doubles >= self.n_edge_double_attr:
                break
            order = order_by_id[att["order_id"]]
            order_at = datetime.fromisoformat(order["order_at"].replace("Z", "+00:00"))
            other_sends = sorted(
                (
                    s for s in self.sends_by_cart_baseline.get(order["cart_id"], [])
                    if s["send_id"] != att["send_id"]
                    and s["campaign_id"] != att["campaign_id"]
                    and s["status"] in ("opened", "clicked") and s["sent_at"]
                    and 0 <= (order_at - datetime.fromisoformat(s["sent_at"].replace("Z", "+00:00"))).total_seconds() <= window_s
                ),
                key=lambda s: (s["sent_at"], s["send_id"]),
            )
            if not other_sends:
                continue
            other = other_sends[0]
            self._att_seq += 1
            bad_att = {
                "attribution_id": pad_id("ATT-", self._att_seq),
                "order_id": att["order_id"],
                "send_id": other["send_id"],
                "campaign_id": other["campaign_id"],
                "attributed_amount": att["attributed_amount"],  # full amount again
                "attribution_window_hours": cfg.ATTRIBUTION_WINDOW_HOURS,
                "is_primary": True,   # anomaly: two primaries
            }
            self.attributions.append(bad_att)
            doubles += 1
            self.ground_truth.append({
                "entity_type": "Attribution",
                "entity_id": bad_att["attribution_id"],
                "issue_type": "attribution_double_counted",
                "description": f"Order {att['order_id']} has two primary attributions ({att['campaign_id']} and {other['campaign_id']})",
                "expected_decision": "exactly one is_primary=true per order; secondary should be is_primary=false or removed",
            })
        self.stats["attribution_doubles_injected"] = doubles

        # --- 4. Cart total stale after quantity update ---
        # Change a line quantity but leave cart.total_amount unchanged
        for k in range(self.n_edge_stale):
            cart = self.carts[k * 17 % len(self.carts)]
            lines = [l for l in self.cart_lines if l["cart_id"] == cart["cart_id"]]
            if not lines:
                continue
            line = lines[0]
            old_qty = line["quantity"]
            line["quantity"] = old_qty + 2
            line["line_total"] = round(line["quantity"] * line["unit_price"], 2)
            # Intentionally do NOT update cart["total_amount"]
            self.ground_truth.append({
                "entity_type": "Cart",
                "entity_id": cart["cart_id"],
                "issue_type": "cart_total_stale_after_quantity_update",
                "description": f"CartLine {line['cart_line_id']} quantity changed but Cart.total_amount was not recalculated",
                "expected_decision": f"Cart.total_amount should equal sum of line_totals (currently stale)",
            })

        print(f"  → {len(self.ground_truth)} ground-truth anomaly records")

    # ------------------------------------------------------------------
    # 8. Validation
    # ------------------------------------------------------------------
    def validate(self) -> Dict[str, Any]:
        print("Running validation …")
        issues = []

        # PK uniqueness
        for name, rows, key in [
            ("Customer", self.customers, "customer_id"),
            ("Cart", self.carts, "cart_id"),
            ("SendAttempt", self.sends, "send_id"),
            ("Order", self.orders, "order_id"),
        ]:
            ids = [r[key] for r in rows]
            if len(ids) != len(set(ids)):
                issues.append(f"Duplicate PKs in {name}")

        # FK integrity (sample)
        cust_ids = {c["customer_id"] for c in self.customers}
        for c in self.carts:
            if c["customer_id"] not in cust_ids:
                issues.append(f"Cart {c['cart_id']} references missing customer")

        # Cart total reconciliation (excluding the deliberately stale ones)
        stale_ids = {
            g["entity_id"] for g in self.ground_truth
            if g["issue_type"] == "cart_total_stale_after_quantity_update"
        }
        line_sum = defaultdict(float)
        for l in self.cart_lines:
            line_sum[l["cart_id"]] += l["line_total"]
        for cart in self.carts:
            if cart["cart_id"] in stale_ids:
                continue
            expected = round(line_sum[cart["cart_id"]], 2)
            if abs(cart["total_amount"] - expected) > 0.02:
                issues.append(f"Cart {cart['cart_id']} total mismatch: {cart['total_amount']} vs {expected}")

        # Date ordering + customer-before-cart
        for cart in self.carts:
            created = datetime.fromisoformat(cart["created_at"].replace("Z", "+00:00"))
            updated = datetime.fromisoformat(cart["last_updated_at"].replace("Z", "+00:00"))
            if updated < created:
                issues.append(f"Cart {cart['cart_id']} last_updated < created")
            cust = self.customer_by_id.get(cart["customer_id"])
            if cust:
                cust_created = datetime.fromisoformat(cust["created_at"].replace("Z", "+00:00"))
                if created < cust_created:
                    issues.append(f"Cart {cart['cart_id']} created before customer {cart['customer_id']}")

        # --- Checks for follow-up messages, frequency cap and attribution ---------------
        gt_ids = defaultdict(set)
        for g in self.ground_truth:
            gt_ids[g["issue_type"]].add(g["entity_id"])
        injected_sends = gt_ids["message_sent_after_opt_out"]
        injected_atts = gt_ids["attribution_double_counted"]

        def _t(x: str) -> datetime:
            return datetime.fromisoformat(x.replace("Z", "+00:00"))

        # message_id: unique, MSG-<cart_id>-NN and consistent with the cart_id column
        seen_msg = set()
        for sd in self.sends:
            mid = sd["message_id"]
            if mid in seen_msg:
                issues.append(f"Duplicate message_id {mid}")
            seen_msg.add(mid)
            if not mid.startswith(f"MSG-{sd['cart_id']}-"):
                issues.append(f"Send {sd['send_id']} message_id {mid} does not match cart {sd['cart_id']}")

        # Frequency cap: never more than MAX non-suppressed sends per customer+channel in any 7-day window
        by_cc = defaultdict(list)
        for sd in self.sends:
            if sd["status"] != "suppressed" and sd["send_id"] not in injected_sends:
                by_cc[(sd["customer_id"], sd["channel"])].append(_t(sd["scheduled_at"]))
        win = timedelta(days=cfg.FREQUENCY_WINDOW_DAYS)
        for key, times in by_cc.items():
            times.sort()
            for idx, t in enumerate(times):
                in_win = sum(1 for u in times[: idx + 1] if t - u < win)
                if in_win > cfg.MAX_SENDS_PER_CUSTOMER_PER_WINDOW:
                    issues.append(f"Frequency cap exceeded for {key}")
                    break

        # No message sent after the cart's order (those are suppressed as already_converted)
        order_at_by_cart = {o["cart_id"]: _t(o["order_at"]) for o in self.orders if o["cart_id"]}
        for sd in self.sends:
            oa = order_at_by_cart.get(sd["cart_id"])
            if oa and sd["status"] != "suppressed" and sd["send_id"] not in injected_sends \
                    and _t(sd["scheduled_at"]) >= oa:
                issues.append(f"Send {sd['send_id']} scheduled after order for {sd['cart_id']}")

        # Attribution: exactly one primary per order (except labelled doubles) and the credited
        # send is inside the attribution window before the order
        order_by_id_v = {o["order_id"]: o for o in self.orders}
        send_by_id_v = {sd["send_id"]: sd for sd in self.sends}
        primaries = defaultdict(list)
        for a in self.attributions:
            if a["is_primary"]:
                primaries[a["order_id"]].append(a["attribution_id"])
            o = order_by_id_v.get(a["order_id"])
            sd = send_by_id_v.get(a["send_id"])
            if o is None or sd is None or not sd["sent_at"]:
                issues.append(f"Attribution {a['attribution_id']} has missing order/send")
                continue
            delta = (_t(o["order_at"]) - _t(sd["sent_at"])).total_seconds()
            if not (0 <= delta <= cfg.ATTRIBUTION_WINDOW_HOURS * 3600):
                issues.append(f"Attribution {a['attribution_id']} outside window")
        for oid_, ids in primaries.items():
            if len(ids) > 1 and not all(i in injected_atts for i in ids[1:]):
                issues.append(f"Order {oid_} has multiple primary attributions not labelled in ground truth")

        report = {
            "validation_passed": len(issues) == 0,
            "issue_count": len(issues),
            "issues_sample": issues[:20],
            "row_counts": {
                "customers": len(self.customers),
                "consents": len(self.consents),
                "sessions": len(self.sessions),
                "carts": len(self.carts),
                "cart_lines": len(self.cart_lines),
                "campaigns": len(self.campaigns),
                "templates": len(self.templates),
                "sends": len(self.sends),
                "message_events": len(self.events),
                "orders": len(self.orders),
                "attributions": len(self.attributions),
                "ground_truth": len(self.ground_truth),
            },
            "business_stats": self.stats,
        }
        return report

    # ------------------------------------------------------------------
    # 9. Export
    # ------------------------------------------------------------------
    def to_dataframes(self) -> Dict[str, pd.DataFrame]:
        return {
            "customers": pd.DataFrame(self.customers),
            "consents": pd.DataFrame(self.consents),
            "sessions": pd.DataFrame(self.sessions),
            "carts": pd.DataFrame(self.carts),
            "cart_lines": pd.DataFrame(self.cart_lines),
            "campaigns": pd.DataFrame(self.campaigns),
            "message_templates": pd.DataFrame(self.templates),
            "send_attempts": pd.DataFrame(self.sends),
            "message_events": pd.DataFrame(self.events),
            "orders": pd.DataFrame(self.orders),
            "attributions": pd.DataFrame(self.attributions),
            "ground_truth": pd.DataFrame(self.ground_truth),
        }

    def export(self, out_dir: Path):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dfs = self.to_dataframes()

        # CSV
        csv_dir = out_dir / "csv"
        csv_dir.mkdir(exist_ok=True)
        for name, df in dfs.items():
            df.to_csv(csv_dir / f"{name}.csv", index=False)

        # JSON (records)
        json_dir = out_dir / "json"
        json_dir.mkdir(exist_ok=True)
        for name, df in dfs.items():
            df.to_json(json_dir / f"{name}.json", orient="records", indent=2, date_format="iso")

        # SQL seed (sample INSERT statements — full data is in CSV/JSON)
        sql_path = out_dir / "seed.sql"
        sample_n = 100
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write("-- Synthetic seed data for Abandoned Cart Recovery\n")
            f.write(f"-- Generated with seed={self.seed}, scale={self.scale}\n")
            f.write(f"-- Sample of {sample_n} rows per table (full data in csv/ and json/)\n\n")
            for name in ["customers", "consents", "carts", "send_attempts",
                         "message_events", "orders", "attributions", "ground_truth"]:
                df = dfs.get(name)
                if df is None or df.empty:
                    continue
                f.write(f"-- {name} ({len(df)} total rows, showing up to {sample_n})\n")
                cols = ", ".join(df.columns)
                for _, row in df.head(sample_n).iterrows():
                    vals = []
                    for v in row:
                        if pd.isna(v) or v is None:
                            vals.append("NULL")
                        elif isinstance(v, (int, float, bool)):
                            vals.append(str(v).upper() if isinstance(v, bool) else str(v))
                        else:
                            vals.append("'" + str(v).replace("'", "''") + "'")
                    f.write(f"INSERT INTO {name} ({cols}) VALUES ({', '.join(vals)});\n")
                f.write("\n")

        # Manifest + checksums
        manifest = {
            "generator": "AbandonedCartGenerator",
            "version": "1.0",
            "seed": self.seed,
            "scale": self.scale,
            "generated_at": iso(datetime.now(timezone.utc)),
            "files": {},
            "validation": self.validate(),
        }
        for name, df in dfs.items():
            manifest["files"][name] = {
                "rows": len(df),
                "checksum_sha256_16": checksum_df(df),
                "csv": f"csv/{name}.csv",
                "json": f"json/{name}.json",
            }

        with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Human-readable validation summary
        with open(out_dir / "validation_summary.txt", "w", encoding="utf-8") as f:
            f.write("VALIDATION SUMMARY\n")
            f.write("=" * 60 + "\n")
            f.write(json.dumps(manifest["validation"], indent=2))
            f.write("\n")

        print(f"Exported to {out_dir}")
        return manifest

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------
    def run(self, out_dir: Path):
        print(f"=== Abandoned Cart Recovery Generator ===")
        print(f"Seed : {self.seed}")
        print(f"Scale: {self.scale}  →  ~{self.n_carts:,} carts, target abandoned {self.n_abandoned_target:,}")
        print()

        self.generate_products()
        self.generate_customers_and_consents()
        self.generate_sessions_carts_lines()
        self.generate_campaigns_and_templates()
        self.generate_sends()
        self.generate_orders_and_attribution()
        self.inject_edge_cases()

        manifest = self.export(out_dir)
        print("\nDone.")
        return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Abandoned Cart Recovery synthetic data generator")
    parser.add_argument("--scale", type=float, default=0.02,
                        help="Volume scale factor (1.0 = full 50k carts). Default 0.02 for quick demo.")
    parser.add_argument("--seed", type=int, default=cfg.SEED)
    parser.add_argument("--out", type=str, default="data/output",
                        help="Output directory")
    parser.add_argument("--full", action="store_true",
                        help="Shortcut for --scale 1.0")
    args = parser.parse_args()

    scale = 1.0 if args.full else args.scale
    out = Path(args.out)

    gen = AbandonedCartGenerator(scale=scale, seed=args.seed)
    gen.run(out)


if __name__ == "__main__":
    main()
