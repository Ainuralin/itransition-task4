from datetime import datetime
from decimal import Decimal
import io
import json
import zipfile
import pandas as pd
import pytest
from analyze import ROOT, money_cents, parse_timestamp, reconcile_users, author_set


@pytest.mark.parametrize(
    "raw,cents",
    [
        ("$35¢25", 3525),
        ("35$25¢", 3525),
        ("35.25 USD", 3525),
        ("€22¢25", 2670),
        ("EUR37.50", 4500),
        ("39€25¢", 4710),
        ("17. EUR", 2040),
        ("USD 0", 0),
    ],
)
def test_monetary_formats(raw, cents):
    assert money_cents(raw) == cents


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("09:28,10-Dec-2025", datetime(2025, 12, 10, 9, 28)),
        ("2025-06-25;05:00:01 A.M.", datetime(2025, 6, 25, 5, 0, 1)),
        ("10:31:43 P.M. 2026-01-14", datetime(2026, 1, 14, 22, 31, 43)),
        ("12/02/25, 09:05:54 pm", datetime(2025, 12, 2, 21, 5, 54)),
        ("10.12.2025 10:59:59", datetime(2025, 12, 10, 10, 59, 59)),
        ("Fri Apr 10 15:32:26 2026", datetime(2026, 4, 10, 15, 32, 26)),
    ],
)
def test_date_conventions(raw, expected):
    assert parse_timestamp(raw) == expected


@pytest.mark.parametrize("raw", ["", "NULL", "today", "12:30", "2025-99-99 12:00"])
def test_bad_dates_never_become_today(raw):
    assert pd.isna(parse_timestamp(raw))


def test_each_field_can_change_and_ids_survive():
    base = {
        "id": 1,
        "name": "Reader",
        "address": "Main Street",
        "phone": "123-456",
        "email": "x@example.test",
    }
    rows = [base]
    for i, field in enumerate(["name", "address", "phone", "email"], 2):
        rows.append({**base, "id": i, field: "999" if field == "phone" else "Changed"})
    users, _ = reconcile_users(pd.DataFrame(rows))
    assert users.customer_id.nunique() == 1
    assert users.iloc[0].alias_ids == [1, 2, 3, 4, 5]


def test_missing_values_are_not_identity_evidence():
    rows = [
        {"id": 1, "name": "A", "address": None, "phone": "123", "email": "a@test"},
        {"id": 2, "name": "B", "address": None, "phone": "123", "email": "a@test"},
    ]
    users, _ = reconcile_users(pd.DataFrame(rows))
    assert users.customer_id.nunique() == 2


def test_author_sets_ignore_order_and_repeats():
    assert author_set("John, Paul, John") == author_set("Paul, John")
    assert author_set("John") != author_set("John, Paul")


def test_complete_dataset_independent_revenue_and_invariants():
    results = json.loads((ROOT / "dist/data.json").read_text())
    with zipfile.ZipFile(ROOT / "data/data.zip") as z:
        assert len(results) == 5
        for r in results:
            raw = pd.read_parquet(io.BytesIO(z.read(r["store"] + "/orders.parquet")))
            # Independent price parser, not calling money_cents.
            total = 0
            import re

            for row in raw.itertuples():
                p = str(row.unit_price)
                digits = re.findall(r"\d+", p)
                whole = int(digits[0])
                frac = digits[1] if len(digits) > 1 else ""
                amount = (
                    Decimal(whole) + Decimal("0." + frac) if frac else Decimal(whole)
                )
                if "€" in p or "EUR" in p.upper():
                    amount *= Decimal("1.2")
                cents = int(
                    (amount * 100).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
                )
                total += cents * int(row.quantity)
            assert total == r["revenue_cents"]
            assert len(raw) == r["order_count"]
            assert r["quality"]["rejected_orders"] == 0
            assert round(sum(d["revenue"] for d in r["daily"]) * 100) == total
            assert len(r["top_days"]) == 5
            assert r["top_days"] == sorted(
                r["top_days"], key=lambda d: (-d["revenue"], d["date"])
            )
            assert (
                r["unique_users"]
                == r["quality"]["input_users"] - r["quality"]["reconciled_profiles"]
            )
