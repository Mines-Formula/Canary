# Canary

Uptime monitoring for fsaelinux.

## Layout

    emitter/emitter.py          runs on fsaelinux, sends heartbeats
    heartbeat-server/app.py     runs on EC2, FastAPI, collects them
    docker-compose.yml          both services, one profile each
    run.sh                      picks the right profile for the host

## Setup

Same `.env` on both machines:

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
alive. To add one, append to `HTTP_SERVICES` in `emitter/emitter.py`.

## Notes

The emitter needs `network_mode: host` to reach those ports and a read-only
mount of `/` at `/host` to see the real disks, not the container's. Both are set
in the compose file.

Heartbeats are not persisted. Restarting the server empties `/status` until the
next round of pings lands.
