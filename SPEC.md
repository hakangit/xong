# Product specification

Xong means “done.” It is a calm task list for people and the agents that support them.
The interface stays simple; delegation, organizational knowledge, and automation live
behind APIs and optional server capabilities.

## Product principles

1. A task may include one concrete `next_action`; vague tasks receive a gentle nudge.
2. Each person can choose at most three focus tasks for the day.
3. Completion is the primary interaction: immediate motion, sound, and positive feedback.
4. Overdue work rolls forward without alarm colors or guilt language.
5. A task may record a due time and a short when/where implementation intention.
6. Vietnamese, English, and Simplified Chinese are first-class UI languages.

## Core

The core server provides users, lists, tasks, focus, completion events, streaks, weekly
recaps, OpenAPI, a web client, OIDC authentication, trusted reverse-proxy authentication,
and scoped agent API keys. New users receive a localized default list.

## Optional capabilities

- `files`: task attachments and governed spreadsheet field bindings.
- `org`: people, skills, teaching sessions, usage, and decision traces.
- `assistant`: commands routed to the authenticated person's linked agent.
- `mcp`: authenticated Streamable HTTP tools for task operations.
- `a2a`: authenticated JSON-RPC task operations and agent discovery.

Capabilities are enabled explicitly with `XONG_PLUGINS` and advertised through
`/.well-known/xong-config`. Disabled capability routes return 404.

## Persistence and synchronization

PostgreSQL is authoritative. Alembic migrations form one linear chain and deployments
must upgrade before application readiness. Clients may cache data locally and queue failed
writes, but authorization and business rules remain server-side.

## Non-goals

The current product does not include calendar synchronization, notifications, shared
human task assignment, comments, tags, priorities, or recurring tasks.

## Release checks

- Core-only and all-capability test matrices pass against PostgreSQL through Alembic.
- Ruff and whitespace validation pass.
- The container starts from an empty database and `/readyz` reports the expected schema.
- Disabled routes are absent; enabled MCP and A2A operations remain scoped to the
  authenticated principal.
