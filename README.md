# Canary

Uptime monitoring for fsaelinux.

Additional Windows hosts are registered with `[[hosts]]` in `services.toml`.

## Layout

    emitter/emitter.py          runs on fsaelinux, sends heartbeats
    heartbeat-server/app.py     runs on EC2, FastAPI, collects them
    docker-compose.yml          both services, one profile each
    run.sh                      picks the right profile for the host

## Setup

Use the host-specific `.env.emitter.example` on fsaelinux and `.env.server.example`
on EC2; the `API_KEY` must match. Keep Slack credentials only on EC2.
The Linux emitter configuration includes:

    CANARY_URL=http://<ec2-host>:8000/heartbeat
    SERVICE_NAME=fsaelinux
    PING_INTERVAL=10
    API_KEY=<shared secret>

## Running

    ./run.sh

Logs and teardown:

    docker compose logs -f
    docker compose down

## Endpoints

`POST /heartbeat` takes `{service, status, message}` and requires the
`X-API-Key` header.

`GET /status` returns every service with a state, and is open. State comes from
the age of the last heartbeat: under 15s is `UP`, under 30s is `STALE`, past that
or any non-ok status is `DOWN`.

## Monitored

The host itself (disks, memory, load, boot time) plus HTTP checks against
MFHome, InfluxDB, Wiki, ThePipeline, and Grafana. Anything under a 500 counts as
alive. To add one, append an enabled `[[services]]` entry to `services.toml`, deploy
the file to fsaelinux and EC2, and restart their emitter/Canary containers. Retain
retired entries with `enabled = false`.

## Notes

The emitter needs `network_mode: host` to reach those ports and a read-only
mount of `/` at `/host` to see the real disks, not the container's. Both are set
in the compose file.

Heartbeats are not persisted. Restarting the server empties `/status` until the
next round of pings lands.

Canary's own state (open incidents, the pending Slack queue) lives in SQLite on
the `canary-data` volume. Multi-host support migrates that database on first
start, and older versions cannot read the result. To roll EC2 back to a version
from before `[[hosts]]`, check out that version and start it with a fresh
database:

    ./run.sh --fresh

`--fresh` deletes the volume before starting, and only works on EC2.

Canary rebuilds its state from `/status` within a minute. Unsent Slack messages
are lost and any ongoing outage is announced again as a new alert.
