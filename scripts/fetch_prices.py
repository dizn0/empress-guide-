#!/usr/bin/env python3
"""Fetch each item's YunaMS market detail page and grab its headline
"Avg Price" (the 90-day average), then write prices.json at the repo root.

Run automatically by .github/workflows/update-prices.yml, or by hand:
    pip install requests beautifulsoup4
    python scripts/fetch_prices.py
"""
import json, re, sys, time, datetime, pathlib
import requests
from bs4 import BeautifulSoup

BASE = "https://yuna.ms/market"          # detail page = BASE/<itemId>
TIMEOUT = 25
UA = "Mozilla/5.0 (compatible; empress-guide-pricebot/1.0)"

# internal calculator id -> YunaMS item ID
TARGETS = {
    "ws":  "2340000",   # White Scroll
    "cs":  "2049100",   # Chaos Scroll 60%
    "adc": "4251402",   # Advanced Dark Crystal
    "ed":  "4032133",   # Empress' Diamond
    "cry": "4251002",   # Advanced LUK Crystal (stat crystal)
}

MONEY = re.compile(r"([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)


def to_meso(text):
    """'60.9M' -> 60900000, '250.0K' -> 250000, '777' -> 777."""
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


def fetch_avg(sess, item_id):
    """Read the item's detail page and return its 'Avg Price' in mesos."""
    url = f"{BASE}/{item_id}"
    r = sess.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    idx = text.find("Avg Price")
    if idx == -1:
        return 0
    # the average value is the first money token right after the label
    return to_meso(text[idx + len("Avg Price"): idx + len("Avg Price") + 40])


def main():
    sess = requests.Session()
    sess.headers["User-Agent"] = UA

    found = {}
    for key, iid in TARGETS.items():
        try:
            meso = fetch_avg(sess, iid)
            print(f"{key} ({iid}): {meso}")
            if meso > 0:
                found[key] = meso
        except Exception as e:
            print(f"warn: {key} ({iid}) failed: {e}", file=sys.stderr)
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
        "source": BASE,
        "prices": prices,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print("wrote prices.json:", json.dumps(payload))


if __name__ == "__main__":
    main()
