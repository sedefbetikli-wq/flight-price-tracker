
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


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def main():
    now = dt.datetime.now(dt.timezone.utc)

    # GitHub runs every 3 hours.
    # Rotate between four German airports.
    slot = int(now.timestamp()) // 10800
    airport = AIRPORTS[slot % len(AIRPORTS)]

    report = {
        "checked_at_utc": now.isoformat(),
        "airport": airport,
        "api_requests": 0,
        "results": [],
        "error": None
    }

    params = {
        "engine": "google_travel_explore",
        "departure_id": airport,
        "type": 1,
        "travel_duration": 1,
        "currency": "EUR",
        "gl": "de",
        "hl": "en",
        "api_key": API_KEY
    }

    try:
        url = (
            "https://serpapi.com/search.json?"
            + urllib.parse.urlencode(params)
        )

        report["api_requests"] = 1

        with urllib.request.urlopen(url, timeout=90) as response:
            data = json.load(response)

        if data.get("error"):
            raise RuntimeError(data["error"])

        today = now.date()

        for item in data.get("destinations", []):
            country = str(item.get("country") or "")
            if country.casefold() in EXCLUDED:
                continue

            destination = item.get("destination_airport") or {}
            code = destination.get("code")
            city = item.get("name")
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

            report["results"].append({
                "origin": airport,
                "destination": code,
                "city": city,
                "country": country,
                "departure_date": start,
                "return_date": end,
                "explore_total_eur": price,
                "source": "Google Flights Explore",
                "link": item.get("link")
            })

        report["results"].sort(
            key=lambda item: item["explore_total_eur"]
        )

    except Exception as error:
        report["error"] = str(error)

    latest_path = DATA_DIR / "latest.json"
    latest_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    history_path = DATA_DIR / "history.json"
    history = load_json(history_path, [])

    existing = {
        (
            item["origin"],
            item["destination"],
            item["departure_date"],
            item["return_date"],
            item["explore_total_eur"]
        )
        for item in history
    }

    new_results = []

    for item in report["results"]:
        key = (
            item["origin"],
            item["destination"],
            item["departure_date"],
            item["return_date"],
            item["explore_total_eur"]
        )

        if key not in existing:
            history.append(item)
            existing.add(key)
            new_results.append(item)

    history_path.write_text(
        json.dumps(history[-500:], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps({
        "airport": airport,
        "api_requests": report["api_requests"],
        "results": len(report["results"]),
        "new_results": len(new_results),
        "error": report["error"]
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

