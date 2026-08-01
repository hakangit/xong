# Contributing

Thank you for improving Xong. Keep changes focused and include tests that show why the
behavior matters.

## Setup

Install Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker, and Docker Compose.

```bash
uv sync --all-extras
docker compose up -d db
DATABASE_URL=postgresql+psycopg://xong:xong@localhost:55432/xong \
  uv run alembic upgrade head
```

## Checks

Before opening a pull request, run both capability modes:

```bash
DATABASE_URL=postgresql+psycopg://xong:xong@localhost:55432/xong \
  XONG_PLUGINS= uv run pytest
DATABASE_URL=postgresql+psycopg://xong:xong@localhost:55432/xong \
  XONG_PLUGINS=files,org,assistant,mcp,a2a \
  XONG_ROUTER_BASE=https://router.example uv run pytest
uv run ruff check src tests
uv build
```

Database changes require a linear Alembic migration. Update the expected schema revision
in `src/xong/config.py` and test upgrades from an empty database.

## Public repository boundary

Xong's public repository contains generic product code and examples only. Before committing,
remove or replace any real-world operational data, including:

- Credentials, tokens, keys, cookies, connection strings, or unredacted environment files.
- Organization, customer, employee, tenant, or internal project identifiers.
- Private domains, email addresses, network addresses, hostnames, registry paths, or service URLs.
- Identity-provider application IDs, deployment configuration, logs, database extracts, or seed data.

Use `example.com`, reserved IP ranges, and invented identities in tests and documentation. Keep
organization-specific deployment overlays and integrations in a private repository. If sensitive
data reaches Git history, rotate the credential first; deleting it in a later commit is not enough.

## Pull requests

- Explain the problem and the chosen behavior.
- Keep unrelated refactors out of the change.
- Add or update tests for observable behavior.
- Update user-facing documentation when configuration or protocols change.
- Confirm that the full diff contains only public-safe data.
