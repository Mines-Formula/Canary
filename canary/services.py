"""Shared HTTP service definitions for the emitter and EC2 worker."""

from pathlib import Path
import tomllib
import re
from urllib.parse import urlsplit

DEFAULT_SERVICES_FILE = Path(__file__).resolve().parent.parent / "services.toml"


def normalize_drive(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]:[\\/]?", value):
        raise ValueError("Drives must be local drive roots such as C:\\")
    return value[0].upper() + ":\\"


def load_catalog(path=DEFAULT_SERVICES_FILE, *, host_name=None):
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
    hosts = data.get("hosts", [])
    if not isinstance(hosts, list):
        raise ValueError("hosts must be a list of [[hosts]] tables")
    for host in hosts:
        if not isinstance(host, dict) or set(host) != {"name", "enabled", "drives"}:
            raise ValueError("Each host requires exactly name, enabled, and drives")
        name = host["name"]
        if not isinstance(name, str) or not name or name != name.strip() or name in names or name == host_name:
            raise ValueError("Host names must be unique and must not conflict with services or the primary host")
        if not isinstance(host["enabled"], bool) or not isinstance(host["drives"], list):
            raise ValueError(f"Host {name}: enabled must be boolean and drives must be a list")
        host["drives"] = [normalize_drive(drive) for drive in host["drives"]]
        if len(set(host["drives"])) != len(host["drives"]):
            raise ValueError(f"Host {name}: duplicate drive roots")
        if host["enabled"] and not host["drives"]:
            raise ValueError(f"Host {name}: select at least one local drive before enabling monitoring")
        names.add(name)
    return services, hosts


def load_services(path=DEFAULT_SERVICES_FILE, *, host_name=None):
    return load_catalog(path, host_name=host_name)[0]
