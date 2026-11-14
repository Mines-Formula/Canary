#!/usr/bin/env bash
# Start the Canary services for whichever machine we're on.
#   fsaelinux -> emitter   (profile "edge")
#   EC2       -> heartbeat + canary (profile "server")
# Override with: ./run.sh edge | ./run.sh emitter | ./run.sh server
# Add --fresh on EC2 to delete Canary's database first (see README, Notes).
set -euo pipefail

cd "$(dirname "$0")"

host="$(hostname -f 2>/dev/null || hostname)"

profile=""
fresh=""
for arg in "$@"; do
    if [[ "$arg" == "--fresh" ]]; then fresh=1; else profile="$arg"; fi
done

if [[ -z "$profile" ]]; then
    case "$host" in
        fsaelinux*)      profile=edge ;;
        ip-*|ec2-*)      profile=server ;;
        *)
            echo "Can't tell what host this is: $host" >&2
            echo "Usage: $0 [edge|emitter|server]" >&2
            exit 1
            ;;
    esac
fi

case "$profile" in
    edge|emitter) profile=emitter; services=(emitter) ;;
    server) services=(heartbeat canary) ;;
    *)
        echo "Unknown profile '$profile' (expected edge, emitter or server)" >&2
        exit 1
        ;;
esac

echo "==> $host -> profile '$profile' (services: ${services[*]})"

# Set the profile via env var and name the service outright: older Compose
# versions ignore the --profile flag, which selects nothing at all.
export COMPOSE_PROFILES="$profile"
compose=(docker compose)
if [[ -n "${CANARY_ENV_FILE:-}" ]]; then
    compose+=(--env-file "$CANARY_ENV_FILE")
fi
if [[ -n "$fresh" ]]; then
    if [[ "$profile" != server ]]; then
        echo "--fresh only applies to the server profile" >&2
        exit 1
    fi
    echo "==> --fresh: removing containers and the canary-data volume"
    "${compose[@]}" down -v
fi
"${compose[@]}" up -d --build "${services[@]}"
"${compose[@]}" ps
