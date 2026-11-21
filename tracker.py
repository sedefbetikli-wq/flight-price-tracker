
import os
import json
import datetime as dt
import urllib.parse
import urllib.request
from pathlib import Path

API_KEY = os.environ["SERPAPI_API_KEY"]

AIRPORTS = ["FRA", "HHN", "STR", "FKB"]

EXCLUDED = {
    "PT", "HR", "SI", "BA", "RS", "ME",
    "XK", "AL", "MK", "BG", "RO", "GR"
}

def api(**params):
    params.update(
        api_key=API_KEY,
        currency="EUR",
        hl="en",
        gl="de"
    )
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=90) as response:
        data = json.load(response)
    if "error" in data:
        raise RuntimeError(data["error"])
    return data

def weekends():
    today = dt.date.today()
    dates = []
    for n in range(1, 366):
        day = today + dt.timedelta(days=n)
        if day.weekday() == 4:
            dates.append(day)
    return dates

def flights(origin, destination, date):
    data = api(
        engine="google_flights",
        type=2,
        departure_id=origin,
        arrival_id=destination,
        outbound_date=date.isoformat()
    )
    results = []
    for item in data.get("best_flights", []) + data.get("other_flights", []):
        price = item.get("price")
        legs = item.get("flights", [])
        if not isinstance(price, (int, float)) or price > 40 or not legs:
            continue
        airline = legs[0].get("airline")
        if not airline:
            continue
        results.append({
            "date": str(date),
            "from": origin,
            "to": destination,
            "price": price,
            "airline": airline,
            "source": "Google Flights",
            "link": "https://www.google.com/travel/flights"
        })
    return results

def main():
    all_weekends = weekends()
    hour = int(dt.datetime.now(dt.timezone.utc).timestamp() // 3600)

    # Prioritize the next 90 days, periodically sample later dates.
    near = [
        d for d in all_weekends
        if (d - dt.date.today()).days <= 90
    ]
    pool = all_weekends if hour % 4 == 0 else near
    friday = pool[hour % len(pool)]

    days_out = [friday, friday + dt.timedelta(days=1)]
    days_back = [
        friday + dt.timedelta(days=2),
        friday + dt.timedelta(days=3)
    ]

    report = {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "airports": AIRPORTS,
        "weekend": str(friday),
        "outbound": [],
        "returns": [],
        "weekend_deals": [],
        "errors": []
    }

    # Explore destination discovery from all four airports.
    try:
        discovery = api(
            engine="google_travel_explore",
            departure_id=",".join(AIRPORTS),
            type=1,
            travel_duration=1
        )
        destinations = discovery.get("destinations", [])
    except Exception as error:
        report["errors"].append(str(error))
        destinations = []

    candidates = []
    for place in destinations:
        airport = place.get("destination_airport") or {}
        code = airport.get("code")
        country_code = (place.get("country_code") or "").upper()
        if not code or country_code in EXCLUDED:
            continue
        candidates.append({
            "iata": code,
            "city": place.get("name"),
            "country": place.get("country")
        })

    # Rotate destinations to limit API usage.
    selected = candidates[hour % len(candidates):] if candidates else []
    selected = (selected + candidates)[:1]

    for destination in selected:
        code = destination["iata"]
        for airport in AIRPORTS:
            for date in days_out:
                try:
                    found = flights(airport, code, date)
                    for flight in found:
                        flight.update(destination=destination)
                    report["outbound"].extend(found)
                except Exception as error:
                    report["errors"].append(str(error))

            for date in days_back:
                try:
                    found = flights(code, airport, date)
                    for flight in found:
                        flight.update(destination=destination)
                    report["returns"].extend(found)
                except Exception as error:
                    report["errors"].append(str(error))

    for outgoing in report["outbound"]:
        for returning in report["returns"]:
            if outgoing["to"] != returning["from"]:
                continue
            if outgoing["price"] + returning["price"] <= 60:
                report["weekend_deals"].append({
                    "destination": outgoing["destination"],
                    "outbound": outgoing,
                    "return": returning,
                    "total_eur": outgoing["price"] + returning["price"]
                })

    Path("data").mkdir(exist_ok=True)
    Path("data/latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps({
        "outbound": len(report["outbound"]),
        "returns": len(report["returns"]),
        "weekend_deals": len(report["weekend_deals"]),
        "errors": len(report["errors"])
    }))

if __name__ == "__main__":
    main()
