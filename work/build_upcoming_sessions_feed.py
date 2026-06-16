import argparse
import json
import os
from datetime import datetime, timezone

from bookwhen_api_sync import fetch_events


BOOKWHEN_BASE_URL = "https://bookwhen.com/ctrlaltbreathe"


def booking_url(event_id):
    if not event_id:
        return BOOKWHEN_BASE_URL
    return f"{BOOKWHEN_BASE_URL}/e/{event_id}"


def public_event(row):
    event_id = row.get("event_id", "")
    return {
        "event_id": event_id,
        "title": row.get("title", ""),
        "start_at": row.get("start_at", ""),
        "end_at": row.get("end_at", ""),
        "cancelled_at": row.get("cancelled_at", ""),
        "attendee_limit": row.get("attendee_limit", ""),
        "attendee_count": row.get("attendee_count", ""),
        "waiting_list": row.get("waiting_list", ""),
        "tags": row.get("tags", ""),
        "location": row.get("location", ""),
        "booking_url": booking_url(event_id),
    }


def build_feed(token):
    rows, _raw_pages = fetch_events(token)
    events = [
        public_event(row)
        for row in rows
        if not row.get("cancelled_at")
    ]
    events.sort(key=lambda event: event.get("start_at") or "")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bookwhen",
        "events": events,
    }


def main():
    parser = argparse.ArgumentParser(description="Build public upcoming sessions feed.")
    parser.add_argument("--output", default="public/upcoming-sessions.json")
    args = parser.parse_args()

    token = os.environ.get("BOOKWHEN_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing BOOKWHEN_API_TOKEN")

    feed = build_feed(token)
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=2)
        f.write("\n")
    print(f"Wrote {len(feed['events'])} events to {args.output}")


if __name__ == "__main__":
    main()
