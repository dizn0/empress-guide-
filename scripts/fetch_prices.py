#!/usr/bin/env python3
"""Fetch YunaMS market 7-day average prices for the key Empress loot items
and write prices.json at the repo root.

Run automatically by .github/workflows/update-prices.yml, or by hand:
    pip install requests beautifulsoup4
    python scripts/fetch_prices.py
"""
import json, re, sys, time, datetime, pathlib
import requests
from bs4 import BeautifulSoup

BASE = "https://yuna.ms/market"
PERIOD = 7            # average over the last 7 days (stable-ish)
MAX_PAGES = 30
TIMEOUT = 25
UA = "Mozilla/5.0 (compatible; empress-guide-pricebot/1.0)"

# YunaMS item ID  ->  internal id used by the calculator
TARGETS = {
    "2340000": "ws",    # White Scroll
    "2049100": "cs",    # Chaos Scroll 60%
    "4251402": "adc",   # Advanced Dark Crystal
    "4032133": "ed",    # Empress' Diamond
    "4251002": "cry",   # Advanced LUK Crystal (stat crystal)
}

MONEY = re.compile(r"([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)


def to_meso(text):
    """'40.4M' -> 40400000, '250.0K' -> 250000, '777' -> 777."""
    if not text:
        return 0
    m = MONEY.search(text.replace(",", ""))
    if not m:
        return 0
    num = float(m.group(1))
    suf = (m.group(2) or "").upper()
    if suf == "M":
        num *= 1_000_000
    elif suf == "K":
        num *= 1_000
    return int(round(num))


def avg_col_index(table):
    """Column index whose header mentions 'Avg'. Falls back to 2
    (Item | Latest | Avg | Sales)."""
    head = table.find("tr")
    if not head:
        return 2
    cells = head.find_all(["th", "td"])
    for i, c in enumerate(cells):
        if "avg" in c.get_text(" ", strip=True).lower():
            return i
    return 2


def id_in_row(row):
    """Item ID from the maplestory.io icon URL, or the 'ID: nnn' text."""
    m = re.search(r"/item/(\d+)/", str(row))
    if m:
        return m.group(1)
    m = re.search(r"ID:\s*(\d+)", row.get_text(" ", strip=True))
    return m.group(1) if m else None


def parse_page(html, found):
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        ci = avg_col_index(table)
        for row in table.find_all("tr"):
            iid = id_in_row(row)
            if not iid or iid not in TARGETS or TARGETS[iid] in found:
                continue
            cells = row.find_all(["td", "th"])
            if len(cells) <= ci:
                continue
            meso = to_meso(cells[ci].get_text(" ", strip=True))
            if meso > 0:
                found[TARGETS[iid]] = meso


def main():
    found = {}
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    want = set(TARGETS.values())
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE}?period={PERIOD}&page={page}"
        try:
            r = sess.get(url, timeout=TIMEOUT)
            r.raise_for_status()
        except Exception as e:
            print(f"warn: page {page} failed: {e}", file=sys.stderr)
            continue
        parse_page(r.text, found)
        print(f"page {page}: have {sorted(found)}")
        if want.issubset(found):
            break
        time.sleep(0.5)

    out = pathlib.Path("prices.json")
    prices = {}
    if out.exists():
        try:
            prices = json.loads(out.read_text()).get("prices", {})
        except Exception:
            prices = {}
    prices.update(found)  # keep last-known values for anything missed this run

    if not prices:
        print("error: parsed no prices; leaving file untouched", file=sys.stderr)
        sys.exit(1)

    payload = {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"{BASE}?period={PERIOD}",
        "prices": prices,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print("wrote prices.json:", json.dumps(payload))


if __name__ == "__main__":
    main()
