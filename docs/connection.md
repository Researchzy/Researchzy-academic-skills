# Connect Researchzy

The `researchzy` skill uses Researchzy through a remote MCP server at `https://app.researchzy.com/mcp`. The other six skills work on files and text you give them, with or without a connection.

Every tool requires sign-in and the scopes it declares: `library.read` for search, paper details, the library and the profile; `library.write` for saving papers, creating collections and adding PDFs to library papers; `pdf.read` for PDF download metadata. Never put passwords, cookies, access tokens or signing keys in plugin files. OAuth client IDs are public configuration.

## Sign-in and tokens

- A host that calls a tool without a token receives HTTP 401 with a `WWW-Authenticate` challenge that points to `/.well-known/oauth-protected-resource` and names all three scopes. `initialize` and `tools/list` work without a token, so a host can list the tools before connecting.
- Authorization uses the code flow with PKCE (S256) and the `resource` parameter. The access token lasts one hour. The refresh token is replaced on every refresh and lasts 90 days, so a connection stays signed in while it is used at least once in 90 days. A refresh request may omit `resource`; if it sends one, it must be the MCP URL.
- You can disconnect an app on the Researchzy **Account** page (**Connected apps**). Disconnecting ends that connection's access and refresh tokens at once.

## How hosts identify themselves

Researchzy recognizes a host in one of two ways:

- **Pre-registered client ID**: `paperone-codex` for Codex, with the callback `http://127.0.0.1:8766/callback`. A loopback callback (`127.0.0.1`, `[::1]` or `localhost`) matches on any port.
- **Client ID Metadata Document**: the host sends the HTTPS URL of a JSON document that names it and lists its callbacks. Researchzy accepts documents hosted on `claude.ai`, `claude.com`, `chatgpt.com` and `vscode.dev`, so Claude, Claude Code, ChatGPT and VS Code connect without registration. The consent page shows the host that published the document. Callbacks on another site are ignored; loopback callbacks are allowed, and the consent page then warns that a local app receives the authorization.

## Connect a host without the plugin

| Host | Setup |
|---|---|
| Claude Code | `claude mcp add --transport http researchzy https://app.researchzy.com/mcp`, then `claude mcp login researchzy` (add `--no-browser` on a remote machine) |
| Claude (web or desktop) | **Settings → Connectors → Add custom connector**, with the MCP URL; then connect it |
| VS Code | Add `{"servers": {"researchzy": {"type": "http", "url": "https://app.researchzy.com/mcp"}}}` to the user `mcp.json`, then start the server and approve the sign-in |
| Codex | `codex mcp add researchzy --url https://app.researchzy.com/mcp --oauth-client-id paperone-codex`, then `codex mcp login researchzy` |

Other hosts work when they publish a client metadata document on one of the sites above. To use another host, [open an issue](https://github.com/Researchzy/Researchzy-academic-skills/issues) with its exact callback URLs.

## Install from a local checkout

```sh
# Codex
codex plugin marketplace add /absolute/path/to/Researchzy-academic-skills
codex plugin add researchzy@researchzy

# Claude Code
claude plugin marketplace add /absolute/path/to/Researchzy-academic-skills
claude plugin install researchzy@researchzy
```

If a marketplace with the same name is already configured, remove it first instead of keeping two sources with the same name.
