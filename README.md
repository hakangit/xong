<p align="center">
  <img src="assets/brand/xong-app-icon.svg" alt="Xong terrace logo" width="128">
</p>

<h1 align="center">Xong</h1>

<p align="center"><strong>The quiet joy of done.</strong></p>

Xong is a focused, gamified task app. The core server provides lists, tasks,
today/focus views, a web UI, OIDC authentication, and scoped agent API keys.
Optional capabilities are enabled per deployment with one environment variable.

## Quickstart

Install Docker with Compose, then run:

```bash
docker compose up --build
```

Open <http://localhost:8000>. The Compose stack migrates PostgreSQL with Alembic
and starts core Xong with no plugins. `DEV_USER=demo` supplies local-development
identity; configure OIDC or trusted reverse-proxy identity in production.

## Plugins

Set a comma-separated list such as `XONG_PLUGINS=files,org,mcp,a2a`. An empty
value runs the core task app. Disabled routes are absent and return 404.

| Plugin | Capability | Additional configuration |
| --- | --- | --- |
| `files` | Task attachments and managed-file registry | Writable `XONG_FILES_DIR` |
| `org` | Organization, skill graph, teaching, and traces | None |
| `assistant` | Send commands to a user's own A2A agent | `XONG_ROUTER_BASE`, `XONG_ROUTER_KEY` |
| `mcp` | Authenticated Streamable HTTP MCP server at `/mcp/` | OIDC or an agent API key |
| `a2a` | Authenticated A2A JSON-RPC endpoint and agent card | OIDC or an agent API key |

If `assistant` is requested without `XONG_ROUTER_BASE`, Xong logs a warning and
does not advertise or register that plugin.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL | `postgresql+psycopg://localhost/xong` |
| `XONG_PLUGINS` | Enabled optional capabilities | empty |
| `DEV_USER` | Local-only fixed username | unset |
| `OIDC_ISSUER` | OIDC issuer discovered at runtime | unset |
| `OIDC_AUDIENCE` | Required access-token audience | unset |
| `OIDC_CLIENT_ID` | Client ID advertised to native clients | unset |
| `OIDC_SCOPES` | Scopes advertised to native clients | `openid profile email offline_access` |
| `XONG_ORG_NAME` | Deployment name in autoconfig | `Xong` |
| `XONG_API_BASE` | Public `/api/v1` base advertised to clients | request-derived |
| `XONG_PUBLIC_URL` | Public origin used by MCP and A2A discovery | request-derived |
| `XONG_CORS_ORIGINS` | Comma-separated browser origins | `xong-app://localhost` |
| `XONG_ALLOWED_HOSTS` | Comma-separated MCP HTTP Host values | local development hosts |
| `XONG_FILES_DIR` | Attachment storage root | `/tmp/xong-files` |
| `XONG_MAX_UPLOAD_MB` | Per-file upload limit | `20` |
| `XONG_LINK_DOMAINS` | Domains allowed to auto-link trusted identities | empty |
| `XONG_ROUTER_BASE` | Assistant A2A gateway base URL | unset |
| `XONG_ROUTER_KEY` | Assistant A2A gateway Bearer key | unset |

Agent API keys use the same Bearer header as OIDC tokens and must include an
`X-Acts-For` user allowed by the key. Create one with:

```bash
uv run xong create-key --agent my-agent --acts-for alice
```

## Identity linking

OIDC and trusted reverse-proxy identities are keyed by provider and stable subject, not
by mutable usernames or email addresses. Set `XONG_LINK_DOMAINS` to domains you control
to allow a verified OIDC email or trusted `Remote-Email` header to link a new login to an
existing account. The default is empty, so automatic linking is disabled.

Use `xong link-identity` for an explicit link and `xong merge-users` to reconcile existing
duplicate accounts. See each command's `--help` output before changing production data.

The autoconfig protocol is specified in [docs/xong-config.md](docs/xong-config.md).
OpenAPI is available at <http://localhost:8000/docs>.

## Development

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --all-extras
DATABASE_URL=postgresql+psycopg://localhost/xong uv run alembic upgrade head
DEV_USER=alice uv run uvicorn xong.app:app --reload
```

Tests always build the schema with `alembic upgrade head`:

```bash
DATABASE_URL=postgresql+psycopg://localhost/xong_test XONG_PLUGINS= uv run pytest
DATABASE_URL=postgresql+psycopg://localhost/xong_test \
  XONG_PLUGINS=files,org,assistant,mcp,a2a \
  XONG_ROUTER_BASE=https://router.example uv run pytest
uv run ruff check src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and
[SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## License

Copyright 2026 Nicolas Koehl.

Licensed under the [Apache License 2.0](LICENSE).
