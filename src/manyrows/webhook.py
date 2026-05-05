"""Webhook signature verification helper for inbound deliveries from ManyRows.

Usage (FastAPI / Flask / Django pattern is the same — pull the raw
body bytes off your framework's request)::

    from manyrows.webhook import verify_webhook, WebhookError

    @app.post("/webhooks/manyrows")
    async def webhook(request: Request):
        body = await request.body()
        try:
            verify_webhook(secret=secret, headers=request.headers, body=body)
        except WebhookError as err:
            raise HTTPException(401, detail=err.code)
        # body is verified — json.loads(body) and process

IMPORTANT: read the body as raw bytes BEFORE verifying. The HMAC
covers the exact transmitted bytes; re-serialising parsed JSON
changes whitespace and breaks the check.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Literal

WebhookErrorCode = Literal[
    "missing_timestamp",
    "missing_signature",
    "invalid_timestamp",
    "timestamp_out_of_window",
    "invalid_signature",
]

_HEADER_TIMESTAMP = "x-webhook-timestamp"
_HEADER_SIGNATURE = "x-webhook-signature"
_SIGNATURE_PREFIX = "sha256="
_DEFAULT_TOLERANCE = timedelta(minutes=5)


class WebhookError(Exception):
    """Raised by :func:`verify_webhook` for any failure.

    Inspect ``code`` (one of :data:`WebhookErrorCode` literal strings)
    to distinguish causes — all of them mean "reject the delivery".
    """

    def __init__(self, code: WebhookErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: WebhookErrorCode = code


def verify_webhook(
    *,
    secret: str,
    headers: Mapping[str, str],
    body: bytes | str,
    tolerance: timedelta = _DEFAULT_TOLERANCE,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Verify the HMAC-SHA256 signature and timestamp on an inbound webhook.

    Raises :class:`WebhookError` on any failure; returns ``None`` on
    success. Signature is computed over the canonical string
    ``"<timestamp>.<body>"`` so a replay of an old delivery is
    detectable by the timestamp check even if the body itself is
    unchanged.

    :param secret: Per-webhook secret from the ManyRows admin UI.
    :param headers: Inbound request headers (case-insensitive lookup).
        FastAPI's ``Headers``, Django's ``request.META`` after
        normalisation, raw dict — anything iterable of ``(key, value)``.
    :param body: Raw request body bytes (or str — UTF-8-encoded
        internally).
    :param tolerance: Accept timestamps within ±tolerance of ``now``.
        Default 5 minutes.
    :param now: Override ``datetime.now(timezone.utc)`` (test hook).
    """
    now_fn = now if now is not None else _utcnow

    ts_raw = _header(headers, _HEADER_TIMESTAMP)
    if not ts_raw:
        raise WebhookError("missing_timestamp", "missing X-Webhook-Timestamp header")

    sig_raw = _header(headers, _HEADER_SIGNATURE)
    if not sig_raw:
        raise WebhookError("missing_signature", "missing X-Webhook-Signature header")

    try:
        ts_unix = int(ts_raw)
    except ValueError as exc:
        raise WebhookError(
            "invalid_timestamp", "X-Webhook-Timestamp is not an integer"
        ) from exc

    delta = now_fn() - datetime.fromtimestamp(ts_unix, tz=timezone.utc)
    if delta < -tolerance or delta > tolerance:
        raise WebhookError(
            "timestamp_out_of_window",
            "X-Webhook-Timestamp is outside the accepted window",
        )

    if not sig_raw.startswith(_SIGNATURE_PREFIX):
        raise WebhookError(
            "invalid_signature", "X-Webhook-Signature missing 'sha256=' prefix"
        )
    sig_hex = sig_raw[len(_SIGNATURE_PREFIX) :]

    try:
        provided = bytes.fromhex(sig_hex)
    except ValueError as exc:
        raise WebhookError(
            "invalid_signature", "X-Webhook-Signature is not valid hex"
        ) from exc

    body_bytes = body.encode("utf-8") if isinstance(body, str) else body

    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(ts_raw.encode("utf-8"))
    mac.update(b".")
    mac.update(body_bytes)
    expected = mac.digest()

    # hmac.compare_digest is the constant-time comparison.
    if not hmac.compare_digest(expected, provided):
        raise WebhookError("invalid_signature", "signature mismatch")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _header(headers: Mapping[str, str], name: str) -> str:
    # Case-insensitive lookup — frameworks vary (Django uppercases,
    # Flask preserves, Starlette lowercases). Take the first match.
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return (v or "").strip()
    return ""
