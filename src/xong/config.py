import os
from functools import lru_cache

PLUGINS = ("files", "org", "assistant", "mcp", "a2a")
SCHEMA_REVISION = "009"


@lru_cache
def get_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://localhost/xong",
    )


@lru_cache
def get_dev_user() -> str | None:
    value = os.environ.get("DEV_USER", "").strip()
    return value or None


@lru_cache
def get_oidc_issuer() -> str | None:
    """Identity provider base URL. Any provider publishing OIDC discovery works."""
    return os.environ.get("OIDC_ISSUER", "").strip().rstrip("/") or None


@lru_cache
def get_oidc_audience() -> str | None:
    """Expected `aud`. Unset skips the audience check — fine for a single-client
    deployment, worth setting when the issuer serves several apps."""
    return os.environ.get("OIDC_AUDIENCE", "").strip() or None


@lru_cache
def get_oidc_scopes() -> str:
    return os.environ.get("OIDC_SCOPES", "").strip() or "openid profile email offline_access"


@lru_cache
def get_org_name() -> str:
    return os.environ.get("XONG_ORG_NAME", "").strip() or "Xong"


@lru_cache
def get_public_api_base() -> str | None:
    """Absolute API base advertised to clients, e.g. https://xong.example.com/api/v1."""
    return os.environ.get("XONG_API_BASE", "").strip().rstrip("/") or None


@lru_cache
def get_public_url() -> str | None:
    """Absolute public origin used in protocol discovery documents."""
    return os.environ.get("XONG_PUBLIC_URL", "").strip().rstrip("/") or None


@lru_cache
def get_cors_origins() -> tuple[str, ...]:
    """Origins allowed to call the API from a browser context. The iOS shell
    serves the bundled UI from a custom scheme, so that origin is the default."""
    raw = os.environ.get("XONG_CORS_ORIGINS", "").strip()
    if not raw:
        return ("xong-app://localhost",)
    return tuple(o.strip() for o in raw.split(",") if o.strip())


@lru_cache
def get_oidc_client_id() -> str | None:
    """Native-app client id handed to mobile clients via the config document."""
    return os.environ.get("OIDC_CLIENT_ID", "").strip() or None


@lru_cache
def get_plugins() -> tuple[str, ...]:
    requested = {value.strip().lower() for value in os.environ.get("XONG_PLUGINS", "").split(",")}
    return tuple(name for name in PLUGINS if name in requested)


@lru_cache
def get_link_domains() -> tuple[str, ...]:
    """Email domains allowed to auto-link a new identity to an existing user.
    Empty (the default) disables auto-linking: a fresh deployment must opt in
    for domains it owns, otherwise a matching address on a foreign IdP would
    be an account-takeover path."""
    raw = os.environ.get("XONG_LINK_DOMAINS", "").strip()
    return tuple(d.strip().lower() for d in raw.split(",") if d.strip())


@lru_cache
def get_allowed_hosts() -> tuple[str, ...]:
    raw = os.environ.get("XONG_ALLOWED_HOSTS", "").strip()
    if not raw:
        return ("localhost", "127.0.0.1", "testserver")
    return tuple(host.strip() for host in raw.split(",") if host.strip())


DEFAULT_LIST_NAME = "Việc của tôi"
FOCUS_MAX = 3


@lru_cache
def get_files_dir() -> str:
    # Persistent attachment root. Each user
    # gets their own subfolder under here, so the tree is browsable per person.
    return os.environ.get("XONG_FILES_DIR", "").strip() or "/tmp/xong-files"


# Upload guards (keep uploads bounded).
MAX_UPLOAD_BYTES = int(os.environ.get("XONG_MAX_UPLOAD_MB", "20")) * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel", "application/msword",
    "text/plain", "text/csv",
    "application/zip",
}
