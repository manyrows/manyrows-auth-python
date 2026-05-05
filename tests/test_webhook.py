"""Tests for the webhook signature verifier."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from manyrows import WebhookError, verify_webhook

SECRET = "whsec_test_supersecret_please_rotate"


def sign(secret: str, ts: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), digestmod=hashlib.sha256)
    mac.update(ts.encode())
    mac.update(b".")
    mac.update(body)
    return "sha256=" + mac.digest().hex()


def headers(ts: str = "", sig: str = "") -> dict[str, str]:
    h: dict[str, str] = {}
    if ts:
        h["X-Webhook-Timestamp"] = ts
    if sig:
        h["X-Webhook-Signature"] = sig
    return h


def at_unix(sec: int) -> Any:
    return lambda: datetime.fromtimestamp(sec, tz=timezone.utc)


class TestVerifyWebhook:
    body: bytes = b'{"event":"user.created","userId":"u_1"}'

    def test_ok_on_fresh_signed_delivery(self) -> None:
        ts = str(int(time.time()))
        sig = sign(SECRET, ts, self.body)
        verify_webhook(secret=SECRET, headers=headers(ts, sig), body=self.body)

    def test_rejects_missing_timestamp(self) -> None:
        with pytest.raises(WebhookError) as exc:
            verify_webhook(secret=SECRET, headers=headers(sig="sha256=abc"), body=self.body)
        assert exc.value.code == "missing_timestamp"

    def test_rejects_missing_signature(self) -> None:
        ts = str(int(time.time()))
        with pytest.raises(WebhookError) as exc:
            verify_webhook(secret=SECRET, headers=headers(ts=ts), body=self.body)
        assert exc.value.code == "missing_signature"

    def test_rejects_malformed_timestamp(self) -> None:
        sig = sign(SECRET, "not-a-number", self.body)
        with pytest.raises(WebhookError) as exc:
            verify_webhook(
                secret=SECRET, headers=headers("not-a-number", sig), body=self.body
            )
        assert exc.value.code == "invalid_timestamp"

    def test_rejects_stale_timestamp(self) -> None:
        ts = "1700000000"
        sig = sign(SECRET, ts, self.body)
        with pytest.raises(WebhookError) as exc:
            verify_webhook(
                secret=SECRET,
                headers=headers(ts, sig),
                body=self.body,
                now=at_unix(1700000000 + 3600),
            )
        assert exc.value.code == "timestamp_out_of_window"

    def test_rejects_future_timestamp(self) -> None:
        ts = str(1700000000 + 3600)
        sig = sign(SECRET, ts, self.body)
        with pytest.raises(WebhookError) as exc:
            verify_webhook(
                secret=SECRET,
                headers=headers(ts, sig),
                body=self.body,
                now=at_unix(1700000000),
            )
        assert exc.value.code == "timestamp_out_of_window"

    def test_rejects_tampered_body(self) -> None:
        ts = str(int(time.time()))
        sig = sign(SECRET, ts, self.body)
        tampered = self.body.replace(b"u_1", b"u_999")
        with pytest.raises(WebhookError) as exc:
            verify_webhook(secret=SECRET, headers=headers(ts, sig), body=tampered)
        assert exc.value.code == "invalid_signature"

    def test_rejects_tampered_timestamp(self) -> None:
        ts_signed = str(int(time.time()))
        sig = sign(SECRET, ts_signed, self.body)
        ts_header = str(int(time.time()) + 1)
        with pytest.raises(WebhookError) as exc:
            verify_webhook(secret=SECRET, headers=headers(ts_header, sig), body=self.body)
        assert exc.value.code == "invalid_signature"

    def test_rejects_wrong_secret(self) -> None:
        ts = str(int(time.time()))
        sig = sign("different-secret", ts, self.body)
        with pytest.raises(WebhookError) as exc:
            verify_webhook(secret=SECRET, headers=headers(ts, sig), body=self.body)
        assert exc.value.code == "invalid_signature"

    def test_rejects_signature_without_prefix(self) -> None:
        ts = str(int(time.time()))
        mac = hmac.new(SECRET.encode(), digestmod=hashlib.sha256)
        mac.update(ts.encode())
        mac.update(b".")
        mac.update(self.body)
        raw_hex = mac.digest().hex()
        with pytest.raises(WebhookError) as exc:
            verify_webhook(secret=SECRET, headers=headers(ts, raw_hex), body=self.body)
        assert exc.value.code == "invalid_signature"

    def test_custom_tolerance(self) -> None:
        ts = "1700000000"
        sig = sign(SECRET, ts, self.body)
        with pytest.raises(WebhookError) as exc:
            verify_webhook(
                secret=SECRET,
                headers=headers(ts, sig),
                body=self.body,
                tolerance=timedelta(seconds=10),
                now=at_unix(1700000000 + 30),
            )
        assert exc.value.code == "timestamp_out_of_window"

    def test_str_body_accepted(self) -> None:
        ts = str(int(time.time()))
        sig = sign(SECRET, ts, self.body)
        verify_webhook(
            secret=SECRET,
            headers=headers(ts, sig),
            body=self.body.decode("utf-8"),
        )

    def test_case_insensitive_headers(self) -> None:
        ts = str(int(time.time()))
        sig = sign(SECRET, ts, self.body)
        h = {
            "x-webhook-timestamp": ts,
            "x-webhook-signature": sig,
        }
        verify_webhook(secret=SECRET, headers=h, body=self.body)
