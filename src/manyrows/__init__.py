"""Official Python SDK for the ManyRows Server API.

Surfaces three things:

* :class:`ManyRowsServer` — the typed server-to-server API client, plus the
  :mod:`manyrows.models` dataclasses it returns.
* :mod:`manyrows.auth` — local JWT verification (``verify_token`` /
  ``verify_token_async``) and header/cookie extraction helpers.
* :mod:`manyrows.secrets` / :mod:`manyrows.webhook` — config-secret decryption
  and inbound webhook signature verification.
"""

from manyrows.auth import bearer_token, mr_at_cookie, verify_token, verify_token_async
from manyrows.client import ManyRowsServer, ManyRowsServerError
from manyrows.models import (
    AuthLogEntry,
    AuthLogsPage,
    BatchUserResult,
    CheckPermissionResult,
    ConfigKey,
    CreateUserResult,
    Delivery,
    DeliveryConfig,
    DeliveryConfigItem,
    DeliveryFlagItem,
    DeliveryFlags,
    FeatureFlag,
    FeatureFlagOverride,
    Identity,
    MagicLinkResult,
    Member,
    MembersList,
    Passkey,
    PermissionSummary,
    RemoveUserResult,
    RoleSummary,
    ServerUser,
    Session,
    User,
    UserField,
    UserFieldValue,
    UserStatus,
    Webhook,
)
from manyrows.secrets import SecretsError, compute_public_jwk_fingerprint, decrypt_secret
from manyrows.webhook import WebhookError, verify_webhook

__version__ = "1.0.0"

__all__ = [
    # Server-to-server client
    "ManyRowsServer",
    "ManyRowsServerError",
    # Models
    "AuthLogEntry",
    "AuthLogsPage",
    "BatchUserResult",
    "CheckPermissionResult",
    "ConfigKey",
    "CreateUserResult",
    "Delivery",
    "DeliveryConfig",
    "DeliveryConfigItem",
    "DeliveryFlagItem",
    "DeliveryFlags",
    "FeatureFlag",
    "FeatureFlagOverride",
    "Identity",
    "MagicLinkResult",
    "Member",
    "MembersList",
    "Passkey",
    "PermissionSummary",
    "RemoveUserResult",
    "RoleSummary",
    "ServerUser",
    "Session",
    "User",
    "UserField",
    "UserFieldValue",
    "UserStatus",
    "Webhook",
    # Auth (local JWT verification + extraction helpers)
    "bearer_token",
    "mr_at_cookie",
    "verify_token",
    "verify_token_async",
    # Secrets
    "SecretsError",
    "compute_public_jwk_fingerprint",
    "decrypt_secret",
    # Webhook
    "WebhookError",
    "verify_webhook",
]
