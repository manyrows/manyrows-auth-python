"""Shared test helpers for the manyrows SDK tests."""

from __future__ import annotations

from typing import Any

import httpx


def make_transport(
    replies: list[dict[str, Any]],
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Build a mock transport that returns the given replies in order.

    Each reply is a dict shaped like:
      - {"status": 200, "json": {...}}
      - {"status": 401, "text": "Unauthorized"}
      - {"error": SomeException()}

    The last reply is reused for any further requests beyond the list.
    Returns ``(transport, captured_requests)``; ``captured_requests`` is
    populated as the transport handles requests so tests can inspect them.
    """
    captured: list[httpx.Request] = []
    idx = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        i = min(idx[0], len(replies) - 1)
        idx[0] += 1
        r = replies[i]
        if "error" in r:
            raise r["error"]
        status = int(r.get("status", 200))
        if "json" in r:
            return httpx.Response(status, json=r["json"])
        return httpx.Response(status, text=str(r.get("text", "")))

    return httpx.MockTransport(handler), captured


async def make_async_transport(
    replies: list[dict[str, Any]],
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Async variant — for symmetry only; ``httpx.MockTransport`` works for both."""
    return make_transport(replies)
