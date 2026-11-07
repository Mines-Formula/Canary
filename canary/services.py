"""Shared HTTP service definitions for the emitter and EC2 worker."""

from pathlib import Path
import tomllib
from urllib.parse import urlsplit

DEFAULT_SERVICES_FILE = Path(__file__).resolve().parent.parent / "services.toml"


def load_services(path=DEFAULT_SERVICES_FILE, *, host_name=None):
    try:
        with open(path, "rb") as file:
            data = tomllib.load(file)
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot load services file {path}: {error}") from error

    services = data.get("services")
    if not isinstance(services, list):
        raise ValueError("Services file must contain [[services]] entries (or services = [] for none)")
    names = set()
    for index, service in enumerate(services, start=1):
        if not isinstance(service, dict):
            raise ValueError(f"Service entry {index} must be a table")
        if set(service) != {"name", "url", "enabled"}:
            raise ValueError(f"Service entry {index} requires exactly name, url, and enabled")
        name, url = service["name"], service["url"]
        if not isinstance(name, str) or not name or name != name.strip():
            raise ValueError(f"Service entry {index} needs a nonempty name without surrounding spaces")
        if name in names or name == host_name:
            raise ValueError(f"Duplicate or reserved host service name: {name}")
        if not isinstance(service["enabled"], bool):
            raise ValueError(f"Service {name}: enabled must be true or false")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if not parsed or parsed.scheme not in {"http", "https"} or not parsed.hostname or url != url.strip():
                raise ValueError("Invalid URL")
            parsed.port  # Validate port as well as hostname.
        except ValueError:
            raise ValueError(f"Service {name} needs a valid HTTP(S) URL") from None
        names.add(name)
    return services
