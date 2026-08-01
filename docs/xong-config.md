# Xong autoconfig document

`GET /.well-known/xong-config` is an unauthenticated deployment-discovery
document. Clients use it to locate the API, configure authentication, and
feature-detect optional server capabilities.

Version 2 has this shape:

```json
{
  "version": 2,
  "name": "Example Organization",
  "api_base": "https://tasks.example.com/api/v1",
  "auth": {
    "type": "oidc",
    "issuer": "https://identity.example.com",
    "client_id": "xong-native",
    "scopes": "openid profile email offline_access"
  },
  "capabilities": ["files", "mcp"]
}
```

Fields:

- `version` is the integer document schema version. Version 2 adds only
  `capabilities`; the version 1 fields retain their names and value shapes.
- `name` is a human-readable deployment name.
- `api_base` is the absolute base URL for the REST API.
- `auth.type` is `oidc` or `none`. `oidc` includes `issuer`, `client_id`, and a
  space-separated `scopes` string. Deployments may include a provider-specific
  audience scope. `none` means client-side token acquisition is disabled,
  usually because a trusted reverse proxy supplies identity.
- `capabilities` is an ordered array containing zero or more of `files`, `org`,
  `assistant`, `mcp`, and `a2a`. Clients must hide capability-specific UI when
  its name is absent instead of probing routes.

Clients should ignore unknown top-level fields and capability names. A client
that only understands version 1 can continue reading the original four fields.
