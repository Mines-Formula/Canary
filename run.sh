#!/usr/bin/env bash
# Start the Canary services for whichever machine we're on.
#   fsaelinux -> emitter   (profile "edge")
#   EC2       -> heartbeat (profile "server")
# Override with: ./run.sh edge | ./run.sh server
set -euo pipefail

cd "$(dirname "$0")"

host="$(hostname -f 2>/dev/null || hostname)"

profile="${1:-}"

if [[ -z "$profile" ]]; then
    case "$host" in
        fsaelinux*)      profile=edge ;;
        ip-*|ec2-*)      profile=server ;;
        *)
            echo "Can't tell what host this is: $host" >&2
            echo "Usage: $0 [edge|server]" >&2
            exit 1
            ;;
    esac
fi

if [[ "$profile" != "edge" && "$profile" != "server" ]]; then
    echo "Unknown profile '$profile' (expected edge or server)" >&2
    exit 1
fi

echo "==> $host -> profile '$profile'"
docker compose --profile "$profile" up -d --build
docker compose --profile "$profile" ps
