
import os
import json
import datetime as dt
import urllib.parse
import urllib.request
from pathlib import Path

API_KEY = os.environ["SERPAPI_API_KEY"]

AIRPORTS = ["FRA", "HHN", "STR", "FKB"]

EXCLUDED = {
    "portugal", "croatia", "slovenia",
    "bosnia and herzegovina", "serbia",
    "montenegro", "kosovo", "albania",
    "north macedonia", "bulgaria",
    "romania", "greece"
}

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default

def main():
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()

    # Exactly one SerpApi request per execution.
    params = {
        "engine": "google_travel_explore",
        "departure_id": ",".join(AIRPORTS),
        "type": 1,
        "travel_duration": 1,
        "travel_mode": 1,
        "currency": "EUR",
        "gl": "de",
        "hl": "en",
        "api_key": API_KEY
    }

    url = (
        "https://serpapi.com/search.json?"
        + urllib.parse.urlencode(params)
    )

    with urllib.request.urlopen(url, timeout=90) as response:
        data = json.load(response)

    if data.get("error"):
        raise RuntimeError(data["error"])

    results = []

    for item in data.get("destinations", []):
        country = str(item.get("country") or "")
        if country.casefold() in EXCLUDED:
            continue

        airport = item.get("destination_airport") or {}
        code = airport.get("code")
        city = item.get("name")
        airline = item.get("airline")
        price = item.get("flight_price")
        start = item.get("start_date")
        end = item.get("end_date")

        if not all([code, city, country, start, end]):
            continue

        if not isinstance(price, (int, float)):
            continue

        if price > 60:
            continue

        try:
            departure = dt.date.fromisoformat(start)
            returning = dt.date.fromisoformat(end)
        except ValueError:
            continue

        if departure < today:
            continue

        if departure.weekday() not in (4, 5):
            continue

        if returning.weekday() not in (6, 0):
            continue

        if (returning - departure).days not in (1, 2, 3):
            continue

        results.append({
            "city": city,
            "country": country,
            "destination_iata": code,
            "departure_date": start,
            "return_date": end,
            "explore_total_eur": price,
            "airline": airline,
            "source": "Google Flights Explore",
            "link": item.get("link"),
            "note": (
                "Explore round-trip result. "
                "Separate outbound and return prices "
                "are not provided."
            )
        })

    results.sort(key=lambda x: x["explore_total_eur"])

    latest = {
        "checked_at_utc": now.isoformat(),
        "searched_airports": AIRPORTS,
        "api_requests": 1,
        "eligible_results": results[:30]
    }

    (DATA_DIR / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    history_path = DATA_DIR / "history.json"
    history = read_json(history_path, [])

    known = {
        (
            x["destination_iata"],
            x["departure_date"],
            x["return_date"],
            x["explore_total_eur"]
        )
        for x in history
    }

    new_results = []

    for item in results:
        key = (
            item["destination_iata"],
            item["departure_date"],
            item["return_date"],
            item["explore_total_eur"]
        )

        if key not in known:
            history.append(item)
            new_results.append(item)
            known.add(key)

    history_path.write_text(
        json.dumps(history[-500:], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps({
        "api_requests": 1,
        "eligible_results": len(results),
        "new_results": len(new_results),
        "best_results": new_results[:5]
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
