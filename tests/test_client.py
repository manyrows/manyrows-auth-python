from __future__ import annotations

import httpx
import pytest

from manyrows import AsyncClient, Client, ManyRowsError

from .conftest import make_transport

BASE_OPTS = {
    "base_url": "https://app.manyrows.com",
    "workspace_slug": "acme",
    "app_id": "app_123",
    "api_key": "mr_test_key",
}

EMPTY_DELIVERY = {
    "workspaceId": "ws",
    "projectId": "p",
    "appId": "app_123",
    "updatedAt": "",
    "config": {"public": [], "private": [], "secrets": []},
    "flags": {"client": [], "server": []},
}


# ===== Constructor =====


class TestConstructor:
    def test_raises_when_required_options_missing(self):
        with pytest.raises(ValueError, match="base_url"):
            Client(**{**BASE_OPTS, "base_url": ""})
        with pytest.raises(ValueError, match="workspace_slug"):
            Client(**{**BASE_OPTS, "workspace_slug": ""})
        with pytest.raises(ValueError, match="app_id"):
            Client(**{**BASE_OPTS, "app_id": ""})
        with pytest.raises(ValueError, match="api_key"):
            Client(**{**BASE_OPTS, "api_key": ""})

    def test_strips_trailing_slashes_from_base_url(self):
        transport, captured = make_transport([{"json": EMPTY_DELIVERY}])
        with httpx.Client(transport=transport) as http:
            client = Client(
                **{**BASE_OPTS, "base_url": "https://app.manyrows.com///"},
                http_client=http,
            )
            client.get_delivery()
        assert (
            str(captured[0].url)
            == "https://app.manyrows.com/x/acme/api/apps/app_123/"
        )
        assert ".com//" not in str(captured[0].url)


# ===== get_delivery =====


class TestGetDelivery:
    def test_parses_delivery_body(self):
        transport, _ = make_transport(
            [
                {
                    "json": {
                        "workspaceId": "ws_1",
                        "projectId": "p_1",
                        "appId": "app_123",
                        "updatedAt": "2026-01-15T10:30:00Z",
                        "config": {
                            "public": [
                                {"key": "theme", "type": "string", "value": "dark"}
                            ],
                            "private": [],
                            "secrets": [{"key": "stripe", "type": "secret", "isSet": True}],
                        },
                        "flags": {
                            "client": [],
                            "server": [{"key": "beta", "enabled": True}],
                        },
                    }
                }
            ]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            d = client.get_delivery()
        assert d.workspace_id == "ws_1"
        assert d.config.public[0].key == "theme"
        assert d.config.public[0].value == "dark"
        assert d.config.secrets[0].is_set is True
        assert d.flags.server[0].enabled is True

    def test_sends_api_key_and_user_agent(self):
        transport, captured = make_transport([{"json": EMPTY_DELIVERY}])
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            client.get_delivery()
        assert captured[0].headers["X-API-Key"] == "mr_test_key"
        assert captured[0].headers["User-Agent"].startswith("manyrows-python/")


# ===== Error handling =====


class TestErrorHandling:
    def test_raises_manyrows_error_with_status_and_body(self):
        transport, _ = make_transport([{"status": 401, "text": "invalid api key"}])
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            with pytest.raises(ManyRowsError) as exc_info:
                client.get_delivery()
        err = exc_info.value
        assert err.status == 401
        assert err.body == "invalid api key"

    def test_wraps_network_errors_into_manyrows_error(self):
        transport, _ = make_transport(
            [{"error": httpx.ConnectError("ECONNREFUSED")}]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            with pytest.raises(ManyRowsError, match="ECONNREFUSED"):
                client.get_delivery()


# ===== Permissions =====


class TestPermissions:
    def test_check_permission_encodes_query_params(self):
        transport, captured = make_transport(
            [{"json": {"allowed": True, "permission": "posts:edit", "accountId": "u_1"}}]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            r = client.check_permission("u_1", "posts:edit")
        assert r.allowed is True
        url = str(captured[0].url)
        assert "/check-permission?" in url
        assert "accountId=u_1" in url
        assert "permission=posts" in url

    def test_has_permission_returns_just_the_boolean(self):
        transport, _ = make_transport(
            [{"json": {"allowed": False, "permission": "x", "accountId": "u_1"}}]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            assert client.has_permission("u_1", "x") is False


# ===== list_members =====


class TestListMembers:
    def test_defaults_page_0_page_size_50(self):
        transport, captured = make_transport(
            [{"json": {"members": [], "total": 0, "page": 0, "pageSize": 50}}]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            client.list_members()
        url = str(captured[0].url)
        assert "page=0" in url
        assert "pageSize=50" in url
        assert "email=" not in url

    def test_passes_provided_page_page_size_email(self):
        transport, captured = make_transport(
            [{"json": {"members": [], "total": 0, "page": 2, "pageSize": 100}}]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            client.list_members(page=2, page_size=100, email="alice@example.com")
        url = str(captured[0].url)
        assert "page=2" in url
        assert "pageSize=100" in url
        assert "email=alice%40example.com" in url

    def test_list_members_by_email_forwards_to_list_members(self):
        transport, captured = make_transport(
            [{"json": {"members": [], "total": 0, "page": 0, "pageSize": 50}}]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            client.list_members_by_email("bob")
        assert "email=bob" in str(captured[0].url)


# ===== get_user / get_user_by_email =====


class TestGetUser:
    def test_get_user_hits_users_with_id_param(self):
        transport, captured = make_transport(
            [
                {
                    "json": {
                        "user": {
                            "id": "u_1",
                            "email": "a@b.com",
                            "enabled": True,
                            "source": "registered",
                        },
                        "roles": [],
                        "permissions": [],
                        "fields": [],
                    }
                }
            ]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            r = client.get_user("u_1")
        assert r.user.id == "u_1"
        assert r.user.email == "a@b.com"
        assert "/users?id=u_1" in str(captured[0].url)

    def test_get_user_by_email_hits_users_with_email_param(self):
        transport, captured = make_transport(
            [
                {
                    "json": {
                        "user": {
                            "id": "u_1",
                            "email": "a@b.com",
                            "enabled": True,
                            "source": "registered",
                        },
                        "roles": [],
                        "permissions": [],
                        "fields": [],
                    }
                }
            ]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            client.get_user_by_email("a@b.com")
        assert "/users?email=a%40b.com" in str(captured[0].url)


# ===== list_user_fields =====


class TestListUserFields:
    def test_returns_user_fields_array(self):
        transport, _ = make_transport(
            [
                {
                    "json": {
                        "userFields": [
                            {
                                "id": "f_1",
                                "key": "name",
                                "valueType": "string",
                                "label": "Name",
                                "status": "active",
                            },
                            {
                                "id": "f_2",
                                "key": "verified",
                                "valueType": "bool",
                                "status": "active",
                            },
                        ]
                    }
                }
            ]
        )
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            fields = client.list_user_fields()
        assert len(fields) == 2
        assert fields[0].key == "name"
        assert fields[0].value_type == "string"

    def test_returns_empty_list_when_user_fields_missing(self):
        transport, _ = make_transport([{"json": {}}])
        with httpx.Client(transport=transport) as http:
            client = Client(**BASE_OPTS, http_client=http)
            assert client.list_user_fields() == []


# ===== Async client =====


class TestAsyncClient:
    async def test_async_get_delivery_works(self):
        transport, _ = make_transport(
            [
                {
                    "json": {
                        "workspaceId": "ws_1",
                        "projectId": "p_1",
                        "appId": "app_123",
                        "updatedAt": "x",
                        "config": {"public": [], "private": [], "secrets": []},
                        "flags": {"client": [], "server": []},
                    }
                }
            ]
        )
        async with httpx.AsyncClient(transport=transport) as http:
            client = AsyncClient(**BASE_OPTS, http_client=http)
            d = await client.get_delivery()
        assert d.workspace_id == "ws_1"

    async def test_async_check_permission(self):
        transport, _ = make_transport(
            [{"json": {"allowed": True, "permission": "p", "accountId": "u_1"}}]
        )
        async with httpx.AsyncClient(transport=transport) as http:
            client = AsyncClient(**BASE_OPTS, http_client=http)
            assert await client.has_permission("u_1", "p") is True

    async def test_async_raises_manyrows_error_on_4xx(self):
        transport, _ = make_transport([{"status": 401, "text": "no"}])
        async with httpx.AsyncClient(transport=transport) as http:
            client = AsyncClient(**BASE_OPTS, http_client=http)
            with pytest.raises(ManyRowsError):
                await client.get_delivery()

    async def test_async_list_members_passes_filter(self):
        transport, captured = make_transport(
            [{"json": {"members": [], "total": 0, "page": 0, "pageSize": 50}}]
        )
        async with httpx.AsyncClient(transport=transport) as http:
            client = AsyncClient(**BASE_OPTS, http_client=http)
            await client.list_members(email="alice")
        assert "email=alice" in str(captured[0].url)


# ===== Context manager =====


class TestContextManagers:
    def test_client_context_manager_closes(self):
        transport, _ = make_transport([{"json": EMPTY_DELIVERY}])
        with Client(**BASE_OPTS, http_client=httpx.Client(transport=transport)) as client:
            client.get_delivery()
        # No exception means __exit__ ran cleanly.

    async def test_async_client_context_manager_closes(self):
        transport, _ = make_transport([{"json": EMPTY_DELIVERY}])
        async with AsyncClient(
            **BASE_OPTS, http_client=httpx.AsyncClient(transport=transport)
        ) as client:
            await client.get_delivery()
