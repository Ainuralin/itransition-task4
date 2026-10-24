"""Clean the bookstore data and calculate results for each store."""

from __future__ import annotations
import argparse
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from pathlib import Path
import pandas as pd
import yaml
from dateutil import parser as dateparser

MISSING = {"", "null", "none", "nan", "n/a", "na"}
FIELDS = ["name", "address", "phone", "email"]
ROOT = Path(__file__).resolve().parent


def clean_text(value):
    if value is None or pd.isna(value):
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return None if value.casefold() in MISSING else value


def normalized(value, field):
    value = clean_text(value)
    if value is None:
        return None
    return re.sub(r"\D", "", value) if field == "phone" else value.casefold()


def money_cents(value):
    """USD/EUR, including $35¢25, 35$25¢ and 35.25 USD."""
    value = clean_text(value)
    if value is None:
        raise ValueError("Missing price")
    currency = "EUR" if "€" in value or "EUR" in value.upper() else "USD"
    if not re.search(r"USD|EUR|[$€]", value, re.I):
        raise ValueError(f"Currency not specified: {value}")
    parts = re.findall(r"\d+(?:\.\d*)?", value)
    if len(parts) == 1:
        amount = Decimal(parts[0])
    elif len(parts) == 2 and "¢" in value and int(parts[1]) < 100:
        amount = Decimal(parts[0]) + Decimal(parts[1]) / 100
    else:
        raise ValueError(f"Unrecognized price: {value}")
    rate = Decimal("1.2") if currency == "EUR" else Decimal("1")
    return int((amount * rate * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_timestamp(value):
    """Parse the timestamp formats used in the orders files."""
    value = clean_text(value)
    if not value:
        return pd.NaT
    value = re.sub(r"([AP])\.M\.", r"\1M", value, flags=re.I)
    value = value.replace(";", " ").replace(",", " ")
    # Some rows put the time before the date, so parse the two parts separately.
    patterns = [
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        (r"\d{1,2}/\d{1,2}/\d{2}(?:\d{2})?", None),
        (r"\d{1,2}\.\d{1,2}\.\d{4}", "%d.%m.%Y"),
        (r"\d{1,2}-[A-Za-z]+-\d{4}", None),
    ]
    try:
        for pattern, fmt in patterns:
            match = re.search(pattern, value)
            if match:
                token = match.group()
                if fmt:
                    day = datetime.strptime(token, fmt)
                else:
                    day = dateparser.parse(
                        token, dayfirst=False, default=datetime(2000, 1, 1)
                    )
                time = re.search(
                    r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:am|pm)?", value, re.I
                )
                if not time:
                    return pd.NaT
                clock = dateparser.parse(time.group(), default=datetime(2000, 1, 1))
                return pd.Timestamp(
                    day.replace(
                        hour=clock.hour,
                        minute=clock.minute,
                        second=clock.second,
                        microsecond=clock.microsecond,
                    )
                )
        # e.g. Fri Apr 10 15:32:26 2026: require an explicit year and month.
        if re.search(r"\b\d{4}\b", value) and re.search(r"[A-Za-z]{3}", value):
            return pd.Timestamp(dateparser.parse(value, default=datetime(2000, 1, 1)))
    except (ValueError, OverflowError):
        pass
    return pd.NaT


def reconcile_users(users):
    """Group profiles that match on three nonmissing fields."""
    users = users.reset_index(drop=True).copy()
    parent = list(range(len(users)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    seen = {}
    edges = []
    for i, row in users.iterrows():
        attrs = [normalized(row[f], f) for f in FIELDS]
        for positions in combinations(range(4), 3):
            values = tuple(attrs[p] for p in positions)
            if any(v is None for v in values):
                continue
            signature = (positions, values)
            if signature in seen:
                j = seen[signature]
                if find(i) != find(j):
                    edges.append(
                        {
                            "user_id_1": int(users.iloc[j]["id"]),
                            "user_id_2": int(row["id"]),
                            "matching_fields": ",".join(FIELDS[p] for p in positions),
                        }
                    )
                union(i, j)
            else:
                seen[signature] = i
    groups = defaultdict(list)
    for i in range(len(users)):
        groups[find(i)].append(int(users.iloc[i]["id"]))
    mapping = {uid: min(ids) for ids in groups.values() for uid in ids}
    users["customer_id"] = users["id"].map(mapping)
    users["alias_ids"] = users["customer_id"].map(
        {min(ids): sorted(ids) for ids in groups.values()}
    )
    return users, edges


def author_set(value):
    value = clean_text(value)
    if value is None:
        return ()
    return tuple(
        sorted({v.strip() for v in value.split(",") if v.strip()}, key=str.casefold)
    )


def analyze_store(z, store, output):
    users = pd.read_csv(z.open(f"{store}/users.csv"), keep_default_na=False)
    books = pd.DataFrame(yaml.safe_load(z.read(f"{store}/books.yaml")))
    books.columns = books.columns.str.lstrip(":")
    orders = pd.read_parquet(io.BytesIO(z.read(f"{store}/orders.parquet")))
    report = {
        "input_users": len(users),
        "input_books": len(books),
        "input_orders": len(orders),
    }
    for frame, name in [(users, "users"), (books, "books"), (orders, "orders")]:
        before = len(frame)
        frame.drop_duplicates(inplace=True)
        report[f"{name}_exact_duplicates_removed"] = before - len(frame)
        if frame["id"].duplicated().any():
            raise ValueError(
                f"{store}: conflicting {name} IDs; manual resolution required"
            )
    for col in FIELDS:
        users[col] = users[col].map(clean_text)
    for col in ["title", "author", "genre", "publisher"]:
        books[col] = books[col].map(clean_text)
    books["year"] = pd.to_numeric(books["year"], errors="coerce").astype("Int64")
    invalid_year = books["year"].notna() & ~books["year"].between(1, 9999)
    report["invalid_publication_years"] = int(invalid_year.sum())
    books.loc[invalid_year, "year"] = pd.NA
    books["author_set"] = books["author"].map(author_set)
    report["missing_book_authors"] = int(books["author"].isna().sum())
    users, edges = reconcile_users(users)
    report["missing_user_addresses"] = int(users["address"].isna().sum())
    orders["timestamp_original"] = orders["timestamp"]
    orders["timestamp"] = pd.to_datetime(orders["timestamp"].map(parse_timestamp))
    orders["shipping"] = orders["shipping"].map(clean_text)
    prices = []
    for p in orders["unit_price"]:
        try:
            prices.append(money_cents(p))
        except ValueError:
            prices.append(None)
    orders["unit_price_cents"] = pd.array(prices, dtype="Int64")
    orders["quantity"] = pd.to_numeric(orders["quantity"], errors="coerce")
    invalid = (
        orders["timestamp"].isna()
        | orders["unit_price_cents"].isna()
        | orders["quantity"].isna()
        | (orders["quantity"] <= 0)
        | (orders["quantity"] % 1 != 0)
        | (orders["unit_price_cents"] < 0)
        | ~orders["user_id"].isin(users["id"])
        | ~orders["book_id"].isin(books["id"])
    )
    report["invalid_dates"] = int(orders["timestamp"].isna().sum())
    report["invalid_prices"] = int(orders["unit_price_cents"].isna().sum())
    report["orphan_user_ids"] = int((~orders["user_id"].isin(users["id"])).sum())
    report["orphan_book_ids"] = int((~orders["book_id"].isin(books["id"])).sum())
    rejected = orders[invalid].copy()
    orders = orders[~invalid].copy()
    orders["quantity"] = orders["quantity"].astype("int64")
    orders["paid_price_cents"] = orders["quantity"] * orders["unit_price_cents"]
    orders["unit_price_usd"] = orders["unit_price_cents"].astype(float) / 100
    orders["paid_price"] = orders["paid_price_cents"].astype(float) / 100
    orders["date"] = orders["timestamp"].dt.strftime("%Y-%m-%d")
    for c in ["year", "month", "day"]:
        orders[c] = getattr(orders["timestamp"].dt, c)
    orders = orders.merge(
        users[["id", "customer_id"]],
        left_on="user_id",
        right_on="id",
        suffixes=("", "_user"),
        validate="many_to_one",
    ).drop(columns="id_user")
    orders = orders.merge(
        books[["id", "author_set", "title", "genre"]],
        left_on="book_id",
        right_on="id",
        suffixes=("", "_book"),
        validate="many_to_one",
    ).drop(columns="id_book")
    daily = orders.groupby("date", as_index=False).agg(
        revenue_cents=("paid_price_cents", "sum"),
        units=("quantity", "sum"),
        orders=("id", "count"),
    )
    # Fill gaps in the daily series with zero sales.
    dates = pd.DataFrame(
        {"date": pd.date_range(daily.date.min(), daily.date.max()).strftime("%Y-%m-%d")}
    )
    daily = dates.merge(daily, on="date", how="left").fillna(0)
    daily["revenue"] = daily["revenue_cents"].astype(float) / 100
    top_days = daily.sort_values(
        ["revenue_cents", "date"], ascending=[False, True]
    ).head(5)
    authors = orders.groupby("author_set", as_index=False).agg(
        units=("quantity", "sum"), revenue_cents=("paid_price_cents", "sum")
    )
    authors["authors"] = authors["author_set"].map(
        lambda v: ", ".join(v) if v else "Unknown authors"
    )
    authors = authors.sort_values(["units", "authors"], ascending=[False, True])
    spending = orders.groupby("customer_id", as_index=False).agg(
        spent_cents=("paid_price_cents", "sum"), units=("quantity", "sum")
    )
    spending["alias_ids"] = spending["customer_id"].map(
        users.drop_duplicates("customer_id").set_index("customer_id")["alias_ids"]
    )
    spending = spending.sort_values(
        ["spent_cents", "customer_id"], ascending=[False, True]
    )
    best = spending[spending.spent_cents.eq(spending.spent_cents.max())]
    popular = authors[authors.units.eq(authors.units.max())]
    result = {
        "store": store,
        "unique_users": int(users.customer_id.nunique()),
        "unique_author_sets": len(set(books["author_set"]) - {()}),
        "revenue_cents": int(orders.paid_price_cents.sum()),
        "sold_books": int(orders.quantity.sum()),
        "order_count": len(orders),
        "top_days": top_days[["date", "revenue"]].to_dict("records"),
        "popular_authors": popular[["authors", "units"]].to_dict("records"),
        "best_buyers": [
            {"ids": r.alias_ids, "spent": int(r.spent_cents) / 100}
            for r in best.itertuples()
        ],
        "daily": daily[["date", "revenue", "units", "orders"]].to_dict("records"),
        "authors": authors[["authors", "units"]].head(20).to_dict("records"),
        "customers": [
            {
                "ids": r.alias_ids,
                "spent": int(r.spent_cents) / 100,
                "units": int(r.units),
            }
            for r in spending.head(20).itertuples()
        ],
        "quality": report,
    }
    report["accepted_orders"] = len(orders)
    report["rejected_orders"] = len(rejected)
    report["reconciliation_links"] = len(edges)
    report["reconciled_profiles"] = len(users) - users.customer_id.nunique()
    destination = output / store
    destination.mkdir(parents=True, exist_ok=True)
    for name, frame in [
        ("users", users),
        ("books", books),
        ("orders", orders),
        ("daily_revenue", daily),
        ("rejected_orders", rejected),
        ("reconciliation_links", pd.DataFrame(edges)),
    ]:
        frame.to_csv(destination / f"{name}.csv", index=False)
    (destination / "summary.json").write_text(
        json.dumps(result, indent=2, default=int), encoding="utf-8"
    )
    assert int(daily.revenue_cents.sum()) == result["revenue_cents"]
    assert int(spending.spent_cents.sum()) == result["revenue_cents"]
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=ROOT / "data/data.zip")
    p.add_argument("--output", type=Path, default=ROOT / "output")
    args = p.parse_args()
    with zipfile.ZipFile(args.input) as z:
        stores = sorted(
            {
                n.split("/")[0]
                for n in z.namelist()
                if re.fullmatch(r"STORE\d+/users.csv", n)
            }
        )
        results = [analyze_store(z, s, args.output) for s in stores]
    (ROOT / "dist").mkdir(exist_ok=True)
    (ROOT / "dist/data.json").write_text(
        json.dumps(results, separators=(",", ":"), default=int), encoding="utf-8"
    )
    for r in results:
        print(
            r["store"],
            r["unique_users"],
            r["unique_author_sets"],
            r["revenue_cents"] / 100,
            r["quality"],
        )


if __name__ == "__main__":
    main()
