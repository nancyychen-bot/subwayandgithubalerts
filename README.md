# MTA Subway Alerts → NTFY

GitHub Actions cron that monitors NYC subway lines **A, C, G** during weekday commute hours and pushes alerts to [ntfy.sh](https://ntfy.sh) when there's a real disruption.

## How it works

Every 5 minutes during commute windows (8-11 AM & 4-7 PM EDT, Mon-Fri), the workflow:

1. Fetches the MTA's JSON alert feed (no API key needed)
2. Filters for real disruptions (Delays, Suspended, Reroute, No Service, Service Change, No Scheduled Service)
3. Skips Planned Work, Station Notices, elevator/escalator alerts, and info-only notices
4. Deduplicates against a cached state file — only notifies on genuinely new alerts
5. Posts to your NTFY topic with priority based on severity

## Setup

1. Fork this repo
2. Add a repo secret `NTFY_TOPIC` with your ntfy.sh topic name
3. Subscribe to that topic in the [ntfy app](https://ntfy.sh/app)
4. The cron runs automatically every 5 minutes — or trigger manually via Actions → "Run workflow"

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `NTFY_TOPIC` | *(required)* | Your ntfy.sh topic name |
| `SEND_RESOLVED` | `false` | Send a notification when an alert clears |
| `STATE_FILE` | `state.json` | Path to the dedup state file |

## Watched lines

A, C, G — edit `WATCHED_LINES` in `subway_alerts.py` to change.

## Stack

- Python 3.11, stdlib only (no pip dependencies)
- GitHub Actions with `actions/cache` for state persistence
- MTA GTFS-RT JSON feed (v2.0, no key required)
