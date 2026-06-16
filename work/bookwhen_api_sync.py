import argparse
import base64
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


API_ROOT = "https://api.bookwhen.com/v2"


def request_json(path, token, params=None):
    url = API_ROOT + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url)
    auth = base64.b64encode((token + ":").encode("ascii")).decode("ascii")
    req.add_header("Authorization", "Basic " + auth)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def relationship_ids(resource, name):
    rel = (resource.get("relationships") or {}).get(name) or {}
    data = rel.get("data")
    if not data:
        return []
    if isinstance(data, list):
        return [item.get("id") for item in data if item.get("id")]
    if isinstance(data, dict) and data.get("id"):
        return [data["id"]]
    return []


def included_lookup(payload):
    lookup = {}
    for item in payload.get("included") or []:
        key = (item.get("type"), item.get("id"))
        lookup[key] = item
    return lookup


def flatten_event(event, included):
    attrs = event.get("attributes") or {}
    location_ids = relationship_ids(event, "location")
    ticket_ids = relationship_ids(event, "tickets")
    location_names = []
    ticket_names = []
    ticket_prices = []

    for location_id in location_ids:
        loc = included.get(("location", location_id)) or {}
        loc_attrs = loc.get("attributes") or {}
        address = loc_attrs.get("address_text") or loc_attrs.get("address")
        if address:
            location_names.append(" / ".join(str(address).splitlines()))

    for ticket_id in ticket_ids:
        ticket = included.get(("ticket", ticket_id)) or {}
        ticket_attrs = ticket.get("attributes") or {}
        title = ticket_attrs.get("title") or ticket_attrs.get("name")
        if title:
            ticket_names.append(str(title).strip())
        price = ticket_attrs.get("cost") or ticket_attrs.get("price")
        if isinstance(price, dict):
            currency = price.get("currency_code") or ""
            net = price.get("net")
            if isinstance(net, int):
                ticket_prices.append(f"{currency} {net / 100:.2f}".strip())
        elif price not in (None, ""):
            ticket_prices.append(str(price).strip())

    return {
        "event_id": event.get("id", ""),
        "title": attrs.get("title", ""),
        "start_at": attrs.get("start_at", ""),
        "end_at": attrs.get("end_at", ""),
        "cancelled_at": attrs.get("cancelled_at", ""),
        "attendee_limit": attrs.get("attendee_limit", ""),
        "attendee_count": attrs.get("attendee_count", ""),
        "waiting_list": attrs.get("waiting_list", ""),
        "tags": "; ".join(attrs.get("tags") or []),
        "location": "; ".join([x for x in location_names if x]),
        "ticket_names": "; ".join(sorted(set(ticket_names))),
        "ticket_prices": "; ".join(sorted(set(ticket_prices))),
        "event_url": (event.get("links") or {}).get("self", ""),
    }


def fetch_events(token):
    offset = 0
    rows = []
    raw_pages = []
    while True:
        payload = request_json(
            "/events",
            token,
            {"include": "location,tickets", "page[offset]": offset},
        )
        raw_pages.append(payload)
        included = included_lookup(payload)
        events = payload.get("data") or []
        rows.extend(flatten_event(event, included) for event in events)
        next_link = (payload.get("links") or {}).get("next")
        if not next_link or not events:
            break
        offset += len(events)
    return rows, raw_pages


def main():
    parser = argparse.ArgumentParser(description="Sync upcoming Bookwhen events.")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--token-file", default=None)
    args = parser.parse_args()

    token = os.environ.get("BOOKWHEN_API_TOKEN", "").strip()
    if not token and args.token_file:
        with open(args.token_file, encoding="utf-8") as f:
            token = f.read().strip()
    if not token:
        print("Missing BOOKWHEN_API_TOKEN or --token-file", file=sys.stderr)
        return 2

    os.makedirs(args.output_dir, exist_ok=True)
    rows, raw_pages = fetch_events(token)
    generated_at = datetime.now(timezone.utc).isoformat()

    csv_path = os.path.join(args.output_dir, "bookwhen_api_upcoming_events.csv")
    json_path = os.path.join(args.output_dir, "bookwhen_api_upcoming_events.json")
    summary_path = os.path.join(args.output_dir, "bookwhen_api_sync_summary.json")

    fields = [
        "event_id",
        "title",
        "start_at",
        "end_at",
        "cancelled_at",
        "attendee_limit",
        "attendee_count",
        "waiting_list",
        "tags",
        "location",
        "ticket_names",
        "ticket_prices",
        "event_url",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": generated_at, "events": rows}, f, indent=2)

    summary = {
        "generated_at": generated_at,
        "event_count": len(rows),
        "page_count": len(raw_pages),
        "csv_path": csv_path,
        "json_path": json_path,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
