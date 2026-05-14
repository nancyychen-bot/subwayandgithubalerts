#!/usr/bin/env python3
"""MTA Subway Alerts -> NTFY notifier. Stdlib only, no external deps."""

import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

FEED_URL = (
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"
    "camsys%2Fsubway-alerts.json"
)
WATCHED_LINES = {"G", "A", "C", "F", "L"}
TRIGGER_TYPES = {
    "Delays",
    "Suspended",
    "Reroute",
    "No Service",
    "Service Change",
    "No Scheduled Service",
}
NO_TRAINS_RE = re.compile(r"^No .+ Trains?$", re.IGNORECASE)
SKIP_RE = re.compile(r"elevator|escalator", re.IGNORECASE)
URGENT_TYPES = {"Suspended", "No Service"}
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
PRUNE_DAYS = 7
SEND_RESOLVED = os.environ.get("SEND_RESOLVED", "false").lower() == "true"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")


def fetch_feed():
    req = urllib.request.Request(
        FEED_URL, headers={"User-Agent": "subway-alerts/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Feed fetch failed: {exc}")
        return None


def strip_html(text):
    return re.sub(r"<[^>]+>", "", html.unescape(text)).strip()


def get_alert_type(alert):
    mercury = alert.get("transit_realtime.mercury_alert", {})
    return mercury.get("alert_type", "")


def get_header_text(alert):
    translations = alert.get("header_text", {}).get("translation", [])
    for t in translations:
        if t.get("language", "en") == "en":
            return strip_html(t.get("text", ""))
    return strip_html(translations[0].get("text", "")) if translations else ""


def is_trigger(alert_type):
    if alert_type in TRIGGER_TYPES:
        return True
    if NO_TRAINS_RE.match(alert_type):
        return True
    return False


def extract_lines(alert):
    lines = set()
    has_route = False
    for ie in alert.get("informed_entity", []):
        if ie.get("agency_id") != "MTASBWY":
            continue
        route = ie.get("route_id")
        if route:
            has_route = True
            if route in WATCHED_LINES:
                lines.add(route)
    if not has_route and not lines:
        return set()
    return lines


def header_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alerts": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def prune_state(state):
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=PRUNE_DAYS)
    ).isoformat()
    state["alerts"] = {
        k: v for k, v in state["alerts"].items() if v["ts"] > cutoff
    }


def send_ntfy(title, body, tags, priority):
    if not NTFY_TOPIC:
        print(f"[dry-run] {title}\n  {body}")
        return
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    req = urllib.request.Request(
        url,
        data=body.encode(),
        headers={
            "Title": title,
            "Priority": priority,
            "Tags": ",".join(tags),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"NTFY {resp.status}: {title}")
    except (urllib.error.URLError, OSError) as exc:
        print(f"NTFY send failed (non-fatal): {exc}")


def main():
    feed = fetch_feed()
    if feed is None:
        print("Feed unavailable, exiting cleanly.")
        sys.exit(0)

    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    entities = feed.get("entity", [])
    current_keys = set()
    new_alerts = []

    for entity in entities:
        alert = entity.get("alert", {})
        alert_type = get_alert_type(alert)

        if not is_trigger(alert_type):
            continue
        if SKIP_RE.search(alert_type):
            continue

        lines = extract_lines(alert)
        if not lines:
            continue

        alert_id = entity.get("id", "")
        header = get_header_text(alert)
        h = header_hash(header)
        state_key = f"{alert_id}:{h}"
        current_keys.add(state_key)

        if state_key not in state["alerts"]:
            new_alerts.append(
                {
                    "state_key": state_key,
                    "type": alert_type,
                    "lines": sorted(lines),
                    "header": header,
                }
            )

    for a in new_alerts:
        lines_str = " ".join(f"[{line}]" for line in a["lines"])
        title = f"{lines_str} {a['type']}"
        priority = "urgent" if a["type"] in URGENT_TYPES else "high"
        tags = ["rotating_light", "train"] + [line.lower() for line in a["lines"]]
        send_ntfy(title, a["header"], tags, priority)
        state["alerts"][a["state_key"]] = {
            "ts": now,
            "lines": a["lines"],
        }

    if SEND_RESOLVED:
        for key, val in list(state["alerts"].items()):
            if key not in current_keys:
                lines_str = " ".join(f"[{l}]" for l in val.get("lines", []))
                send_ntfy(
                    f"{lines_str} resolved",
                    "This alert is no longer in the feed.",
                    ["train", "white_check_mark"],
                    "default",
                )

    prune_state(state)
    save_state(state)
    print(f"Processed {len(entities)} entities, {len(new_alerts)} new alerts sent.")


if __name__ == "__main__":
    main()
