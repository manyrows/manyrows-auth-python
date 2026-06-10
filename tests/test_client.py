import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from manyrows import (
    CODE_CONFLICT,
    CODE_INVITE_PENDING,
    CODE_NOT_FOUND,
    CODE_USER_NOT_SIGNED_IN,
    ManyRowsServer,
    ManyRowsServerError,
    is_code,
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence test output
        pass

    def _handle(self):
        srv = self.server
        srv.last_method = self.command
        srv.last_path = self.path
        srv.last_api_key = self.headers.get("X-API-Key")
        length = int(self.headers.get("Content-Length") or 0)
        srv.last_body = self.rfile.read(length) if length else b""

        status, body = srv.responder(self)
        self.send_response(status)
        if body is None:
            self.end_headers()
            return
        payload = json.dumps(body).encode()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_PATCH = _handle
    do_DELETE = _handle


class ServerClientTest(unittest.TestCase):
    def _client(self, responder):
        srv = HTTPServer(("127.0.0.1", 0), _Handler)
        srv.responder = responder
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        # Cleanups run LIFO: shutdown() stops serving, then server_close()
        # releases the listening socket (avoids ResourceWarning).
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        client = ManyRowsServer(
            base_url=f"http://127.0.0.1:{port}/",  # trailing slash trimmed
            workspace="acme",
            app_id="app-1",
            api_key="mr_abc_secret",
        )
        return client, srv

    def test_check_permission(self):
        client, srv = self._client(
            lambda h: (200, {"allowed": True, "permission": "posts:read", "accountId": "u1"})
        )
        res = client.check_permission("u1", "posts:read")
        self.assertTrue(res.allowed)
        self.assertEqual(res.account_id, "u1")  # camelCase -> snake_case
        self.assertEqual(srv.last_method, "GET")
        self.assertIn("/x/acme/api/v1/apps/app-1/check-permission", srv.last_path)
        self.assertIn("accountId=u1", srv.last_path)
        self.assertEqual(srv.last_api_key, "mr_abc_secret")

    def test_has_permission_returns_bare_boolean(self):
        client, srv = self._client(
            lambda h: (200, {"allowed": True, "permission": "posts:read", "accountId": "u1"})
        )
        self.assertIs(client.has_permission("u1", "posts:read"), True)
        self.assertIn("/check-permission", srv.last_path)

    def test_create_user_posts_body(self):
        client, srv = self._client(
            lambda h: (201, {"user": {"id": "u2", "email": "a@b.com"}, "created": True, "roles": ["editor"]})
        )
        res = client.create_user(email="a@b.com", email_verified=True, roles=["editor"])
        self.assertTrue(res.created)
        self.assertEqual(res.user.id, "u2")
        self.assertEqual(srv.last_method, "POST")
        sent = json.loads(srv.last_body)
        self.assertEqual(sent, {"email": "a@b.com", "emailVerified": True, "roles": ["editor"]})

    def test_non_2xx_raises_typed_error(self):
        client, _ = self._client(lambda h: (404, {"error": "error.notFound", "message": "Not found"}))
        with self.assertRaises(ManyRowsServerError) as ctx:
            client.get_user("missing")
        err = ctx.exception
        self.assertEqual(err.status, 404)
        self.assertEqual(err.code, "error.notFound")
        self.assertEqual(err.message, "Not found")

    def test_delete_field_value_no_content(self):
        seen = {}

        def responder(h):
            seen["method"] = h.command
            seen["path"] = h.path
            return (204, None)

        client, _ = self._client(responder)
        self.assertIsNone(client.delete_user_field_value("f1", "u1"))
        self.assertEqual(seen["method"], "DELETE")
        self.assertTrue(seen["path"].endswith("/user-fields/f1/users/u1"))

    def test_list_users_omits_empty_params(self):
        client, srv = self._client(
            lambda h: (200, {"members": [], "total": 0, "page": 0, "pageSize": 50})
        )
        client.list_users(search="ali")
        self.assertTrue(srv.last_path.endswith("/users?search=ali"))

    def test_constructor_validation(self):
        with self.assertRaises(ValueError):
            ManyRowsServer(base_url="", workspace="a", app_id="b", api_key="c")
        with self.assertRaises(ValueError):
            ManyRowsServer(base_url="x", workspace="a", app_id="b", api_key="")

    def test_request_sets_user_agent(self):
        seen = {}

        def responder(h):
            seen["user_agent"] = h.headers.get("User-Agent")
            return (200, {"allowed": True, "permission": "p", "accountId": "u1"})

        client, _ = self._client(responder)
        client.check_permission("u1", "p")
        self.assertTrue(seen["user_agent"].startswith("manyrows-auth-python/"))

    # ---- Organizations ----

    def test_create_organization_posts_body(self):
        client, srv = self._client(
            lambda h: (
                201,
                {
                    "id": "o1",
                    "appId": "app-1",
                    "name": "Acme",
                    "slug": "acme",
                    "status": "active",
                    "createdAt": "2026-06-07T00:00:00Z",
                },
            )
        )
        org = client.create_organization(name="Acme", owner_user_id="u1")
        self.assertEqual(srv.last_method, "POST")
        self.assertEqual(srv.last_path, "/x/acme/api/v1/apps/app-1/organizations")
        self.assertEqual(json.loads(srv.last_body), {"name": "Acme", "ownerUserId": "u1"})
        self.assertEqual(org.id, "o1")
        self.assertEqual(org.app_id, "app-1")  # camelCase -> snake_case
        self.assertEqual(org.status, "active")

    def test_list_organizations_for_user_query(self):
        client, srv = self._client(
            lambda h: (
                200,
                {"organizations": [{"id": "o1", "name": "Acme", "slug": "acme", "orgRole": "owner"}]},
            )
        )
        orgs = client.list_organizations_for_user("u1")
        self.assertTrue(srv.last_path.endswith("/organizations?userId=u1"))
        self.assertEqual(len(orgs), 1)
        self.assertEqual(orgs[0].org_role, "owner")

    def test_get_organization_not_found(self):
        client, _ = self._client(lambda h: (404, {"error": "error.notFound"}))
        with self.assertRaises(ManyRowsServerError) as ctx:
            client.get_organization("o1")
        err = ctx.exception
        self.assertTrue(is_code(err, CODE_NOT_FOUND))
        self.assertEqual(err.status, 404)
        self.assertEqual(err.code, "error.notFound")

    def test_update_and_delete_organization(self):
        def responder(h):
            if h.command == "PATCH":
                return (200, {"id": "o1", "appId": "app-1", "name": "Renamed", "slug": "acme", "status": "active"})
            return (204, None)

        client, srv = self._client(responder)
        org = client.update_organization("o1", name="Renamed")
        self.assertEqual(org.name, "Renamed")
        self.assertEqual(json.loads(srv.last_body), {"name": "Renamed"})
        # Owner-only delete: the acting end-user must be carried as a query
        # param so the auth server can verify their tier.
        self.assertIsNone(client.delete_organization("o1", "actor-1"))
        self.assertEqual(srv.last_method, "DELETE")
        self.assertTrue(srv.last_path.endswith("/organizations/o1?actorUserId=actor-1"))

    # ---- Organization members ----

    def test_add_organization_member_by_email_not_signed_in(self):
        client, srv = self._client(lambda h: (409, {"error": "error.userNotSignedIn"}))
        with self.assertRaises(ManyRowsServerError) as ctx:
            client.add_organization_member("o1", org_role="admin", email="x@y.com")
        self.assertTrue(is_code(ctx.exception, CODE_USER_NOT_SIGNED_IN))
        self.assertEqual(srv.last_path, "/x/acme/api/v1/apps/app-1/organizations/o1/members")
        self.assertEqual(json.loads(srv.last_body), {"orgRole": "admin", "email": "x@y.com"})

    def test_add_organization_member_success(self):
        client, _ = self._client(
            lambda h: (201, {"userId": "u2", "email": "x@y.com", "orgRole": "admin", "status": "active"})
        )
        m = client.add_organization_member("o1", org_role="admin", email="x@y.com")
        self.assertEqual(m.user_id, "u2")
        self.assertEqual(m.org_role, "admin")

    def test_list_and_get_organization_members(self):
        def responder(h):
            if h.path.endswith("/members/u2"):
                return (200, {"userId": "u2", "orgRole": "admin", "status": "active"})
            return (200, {"members": [{"userId": "u2", "email": "x@y.com", "orgRole": "admin", "status": "active"}]})

        client, _ = self._client(responder)
        members = client.list_organization_members("o1")
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].email, "x@y.com")
        m = client.get_organization_member("o1", "u2")
        self.assertEqual(m.org_role, "admin")

    def test_set_and_remove_organization_member_last_owner(self):
        client, srv = self._client(lambda h: (409, {"error": "error.conflict"}))
        with self.assertRaises(ManyRowsServerError) as ctx:
            client.set_organization_member_role("o1", "u2", "member")
        self.assertTrue(is_code(ctx.exception, CODE_CONFLICT))
        self.assertEqual(srv.last_method, "PATCH")
        self.assertEqual(json.loads(srv.last_body), {"orgRole": "member"})
        with self.assertRaises(ManyRowsServerError) as ctx:
            client.remove_organization_member("o1", "u2")
        self.assertTrue(is_code(ctx.exception, CODE_CONFLICT))
        self.assertEqual(srv.last_method, "DELETE")
        self.assertTrue(srv.last_path.endswith("/organizations/o1/members/u2"))

    # ---- Organization invites ----

    def test_create_organization_invite_posts_optional_fields(self):
        client, srv = self._client(
            lambda h: (
                201,
                {
                    "id": "i1",
                    "email": "x@y.com",
                    "orgRole": "admin",
                    "status": "pending",
                    "createdAt": "t",
                    "expiresAt": "t2",
                },
            )
        )
        inv = client.create_organization_invite(
            "o1", email="x@y.com", org_role="admin", invited_by_user_id="u1"
        )
        self.assertEqual(srv.last_path, "/x/acme/api/v1/apps/app-1/organizations/o1/invites")
        self.assertEqual(
            json.loads(srv.last_body),
            {"email": "x@y.com", "orgRole": "admin", "invitedByUserId": "u1"},
        )
        self.assertEqual(inv.id, "i1")
        self.assertEqual(inv.status, "pending")
        self.assertIsNone(inv.invited_by_email)

    def test_create_organization_invite_omits_unset_fields(self):
        client, srv = self._client(
            lambda h: (
                201,
                {"id": "i1", "email": "x@y.com", "orgRole": "member", "status": "pending"},
            )
        )
        client.create_organization_invite("o1", email="x@y.com")
        self.assertEqual(json.loads(srv.last_body), {"email": "x@y.com"})

    def test_create_organization_invite_duplicate_pending(self):
        client, _ = self._client(lambda h: (409, {"error": "error.invitePending"}))
        with self.assertRaises(ManyRowsServerError) as ctx:
            client.create_organization_invite("o1", email="x@y.com")
        self.assertTrue(is_code(ctx.exception, CODE_INVITE_PENDING))

    def test_list_and_revoke_organization_invites(self):
        def responder(h):
            if h.command == "DELETE":
                return (204, None)
            return (
                200,
                {
                    "invites": [
                        {
                            "id": "i1",
                            "email": "x@y.com",
                            "orgRole": "admin",
                            "status": "pending",
                            "invitedByEmail": "boss@y.com",
                            "createdAt": "t",
                            "expiresAt": "t2",
                        }
                    ]
                },
            )

        client, srv = self._client(responder)
        invites = client.list_organization_invites("o1")
        self.assertTrue(srv.last_path.endswith("/organizations/o1/invites"))
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].email, "x@y.com")
        self.assertEqual(invites[0].invited_by_email, "boss@y.com")
        self.assertIsNone(client.revoke_organization_invite("o1", "i1"))
        self.assertEqual(srv.last_method, "DELETE")
        self.assertTrue(srv.last_path.endswith("/organizations/o1/invites/i1"))


if __name__ == "__main__":
    unittest.main()
