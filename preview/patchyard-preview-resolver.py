#!/usr/bin/env python3
"""Resolve one numbered preview host twice and bind it to one stable IPv4 set."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import sys
import time
from collections.abc import Callable


PREVIEW_HOST = re.compile(r"^(?:[1-9]|[12][0-9]|30)\.preview\.example\.dev$")


class DnsBindingChanged(Exception):
    pass


def resolve_once(host: str) -> tuple[str, ...]:
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(
            host,
            443,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    }
    if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
        raise ValueError("preview resolution is empty or non-public")
    return tuple(sorted(addresses))


def resolve_stable(
    host: str,
    *,
    resolver: Callable[[str], tuple[str, ...]] = resolve_once,
    pause: Callable[[float], None] = time.sleep,
) -> tuple[str, ...]:
    if not PREVIEW_HOST.fullmatch(host):
        raise ValueError("host is outside the preview contract")
    first = resolver(host)
    pause(0.05)
    second = resolver(host)
    if first != second:
        raise DnsBindingChanged
    return first


def main() -> int:
    if len(sys.argv) != 2:
        return 43
    host = sys.argv[1]
    try:
        addresses = resolve_stable(host)
    except DnsBindingChanged:
        print(json.dumps({"schema_version": 1, "state": "dns_binding_changed"}))
        return 42
    except (OSError, ValueError):
        print(json.dumps({"schema_version": 1, "state": "contract_rejected"}))
        return 43
    print(
        json.dumps(
            {
                "schema_version": 1,
                "state": "stable",
                "host": host,
                "addresses": addresses,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
