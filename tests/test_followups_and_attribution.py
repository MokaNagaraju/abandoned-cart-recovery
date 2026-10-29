"""
Behavioural tests for follow-up messages, the frequency cap and double-attribution injection.

Run:  pytest -q        (or: python tests/test_followups_and_attribution.py)
"""
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as cfg
from src.generator import AbandonedCartGenerator


def _run(scale: float = 0.1):
    with tempfile.TemporaryDirectory() as tmp:
        g = AbandonedCartGenerator(scale=scale, seed=cfg.SEED)
        manifest = g.run(Path(tmp) / "out")
    return g, manifest


def test_followups_cap_and_double_attribution():
    g, manifest = _run()

    # validation (PK/FK, totals, message_id uniqueness, cap, attribution window) is clean
    assert manifest["validation"]["validation_passed"], manifest["validation"]["issues_sample"]

    # follow-ups exist: MSG-<cart>-02 and -03
    suffixes = Counter(s["message_id"][-2:] for s in g.sends)
    assert suffixes["02"] > 0 and suffixes["03"] > 0

    # message_id is unique and carries its own cart id
    ids = [s["message_id"] for s in g.sends]
    assert len(ids) == len(set(ids))
    assert all(s["message_id"].startswith(f"MSG-{s['cart_id']}-") for s in g.sends)

    # frequency-cap conflicts exist (3rd message of a chain, or cross-cart for same customer)
    capped = [s for s in g.sends if s["suppression_reason"] == "frequency_cap"]
    assert capped, "expected at least one frequency-cap conflict"
    assert all(s["sent_at"] is None for s in capped)
    assert all(s["status"] == "suppressed" for s in capped)

    # double-counted attribution: rows exist and match the ground-truth labels
    primaries = defaultdict(int)
    for a in g.attributions:
        if a["is_primary"]:
            primaries[a["order_id"]] += 1
    doubled_orders = [o for o, n in primaries.items() if n > 1]
    labelled = [x for x in g.ground_truth if x["issue_type"] == "attribution_double_counted"]
    assert len(doubled_orders) == len(labelled) >= 2

    # ...and the two credited sends belong to different campaigns
    att_by_order = defaultdict(list)
    for a in g.attributions:
        att_by_order[a["order_id"]].append(a)
    for oid in doubled_orders:
        assert len({a["campaign_id"] for a in att_by_order[oid]}) == 2


def test_no_follow_up_after_purchase():
    g, _ = _run()
    order_at = {o["cart_id"]: o["order_at"] for o in g.orders if o["cart_id"]}
    injected = {x["entity_id"] for x in g.ground_truth if x["issue_type"] == "message_sent_after_opt_out"}
    for s in g.sends:
        if s["send_id"] in injected or s["status"] == "suppressed":
            continue
        if s["cart_id"] in order_at:
            assert s["scheduled_at"] < order_at[s["cart_id"]]


if __name__ == "__main__":
    test_followups_cap_and_double_attribution()
    test_no_follow_up_after_purchase()
    print("follow-up / attribution tests PASSED")
