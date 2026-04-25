# manyrows

Official Python SDK for [ManyRows](https://manyrows.com). Mirrors the surface of [`manyrows-go`](https://github.com/manyrows/manyrows-go) and [`@manyrows/manyrows-node`](https://www.npmjs.com/package/@manyrows/manyrows-node).

## Install

```bash
pip install manyrows
```

Requires **Python 3.9+**. Sync and async clients are both included; both use [`httpx`](https://www.python-httpx.org/) under the hood.

## Client

The client wraps the ManyRows Server API. Requires an API key.

```python
from manyrows import Client

client = Client(
    base_url="https://app.manyrows.com",
    workspace_slug="your-workspace",
    app_id="your-app-id",
    api_key="mr_a1b2c3d4_yourSecretKey",
)
```

For async code:

```python
from manyrows import AsyncClient

async with AsyncClient(
    base_url="https://app.manyrows.com",
    workspace_slug="your-workspace",
    app_id="your-app-id",
    api_key="mr_...",
) as client:
    user = await client.get_user("u_123")
```

### Delivery (config + feature flags)

```python
delivery = client.get_delivery()
# delivery.config.public, delivery.config.private, delivery.config.secrets
# delivery.flags.client, delivery.flags.server
```

### Check permission

```python
allowed = client.has_permission(user_id, "posts:edit")

# Or get the full result:
result = client.check_permission(user_id, "posts:edit")
# result.allowed, result.permission, result.account_id
```

### User lookup

```python
# By ID
user = client.get_user(user_id)
# user.user.email, user.roles, user.permissions, user.fields

# By email
user = client.get_user_by_email("user@example.com")
```

### Members

```python
result = client.list_members(page=0, page_size=50)
# result.members, result.total, result.page, result.page_size

# Filter by email substring:
result = client.list_members(page=0, page_size=50, email="alice")

# Or the convenience alias:
result = client.list_members_by_email("alice")
```

### User fields

```python
fields = client.list_user_fields()
# fields[0].key, fields[0].value_type, fields[0].label
```

### Error handling

Non-2xx responses raise `ManyRowsError`:

```python
from manyrows import ManyRowsError

try:
    client.get_user("bogus")
except ManyRowsError as err:
    print(err.status, err.body)
```

## Auth helpers

Validate bearer tokens from your end users by calling the ManyRows `/a/app/me` endpoint, then read the user ID.

### `verify_token`

Returns the user ID on success, `None` if rejected, raises `httpx.HTTPStatusError` on network/server errors:

```python
from manyrows import bearer_token, verify_token

token = bearer_token(request.headers.get("Authorization"))
if not token:
    return Response("Unauthorized", status=401)

try:
    user_id = verify_token(
        token,
        base_url="https://app.manyrows.com",
        workspace_slug="your-workspace",
        app_id="your-app-id",
    )
except Exception:
    return Response("Unauthorized", status=401)  # fail closed on network errors

if user_id is None:
    return Response("Unauthorized", status=401)
```

### Async — `verify_token_async`

```python
from manyrows import verify_token_async

user_id = await verify_token_async(
    token,
    base_url="https://app.manyrows.com",
    workspace_slug="your-workspace",
    app_id="your-app-id",
)
```

### FastAPI

```python
from typing import Annotated
from fastapi import Depends, FastAPI, Header, HTTPException

from manyrows import bearer_token, verify_token_async

app = FastAPI()

async def manyrows_user_id(authorization: Annotated[str | None, Header()] = None) -> str:
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(401)
    try:
        user_id = await verify_token_async(
            token,
            base_url="https://app.manyrows.com",
            workspace_slug="your-workspace",
            app_id="your-app-id",
        )
    except Exception as exc:
        raise HTTPException(401) from exc
    if user_id is None:
        raise HTTPException(401)
    return user_id

@app.get("/api/profile")
async def profile(user_id: Annotated[str, Depends(manyrows_user_id)]):
    return {"user_id": user_id}
```

### Flask

```python
from functools import wraps
from flask import Flask, request, abort, g

from manyrows import bearer_token, verify_token

app = Flask(__name__)

def manyrows_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = bearer_token(request.headers.get("Authorization"))
        if not token:
            abort(401)
        try:
            user_id = verify_token(
                token,
                base_url="https://app.manyrows.com",
                workspace_slug="your-workspace",
                app_id="your-app-id",
            )
        except Exception:
            abort(401)
        if user_id is None:
            abort(401)
        g.manyrows_user_id = user_id
        return f(*args, **kwargs)
    return wrapper

@app.route("/api/profile")
@manyrows_auth
def profile():
    return {"user_id": g.manyrows_user_id}
```

## Custom HTTP client

Inject your own `httpx.Client` / `httpx.AsyncClient` for testing, request tracing, or custom timeout/transport configuration:

```python
import httpx
from manyrows import Client

http = httpx.Client(timeout=30.0, headers={"X-Trace-Id": "abc"})
client = Client(
    base_url="https://app.manyrows.com",
    workspace_slug="your-workspace",
    app_id="your-app-id",
    api_key="mr_...",
    http_client=http,
)
```

When you pass your own client, you own its lifecycle — call `http.close()` (or use it as a context manager) yourself.

## License

[MIT](./LICENSE)
