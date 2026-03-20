# ag-export

Export Antigravity AI conversations locally with built-in privacy redaction.

> [!IMPORTANT]
> **Antigravity enforces a 100-conversation limit.** Active conversations are stored in `~/.gemini/antigravity/conversations/` (max 100). When this limit is reached, the oldest conversations are moved to `~/.gemini/antigravity/implicit/` (also max 100). Conversations beyond this 200-total cap are **permanently deleted** and cannot be recovered. **Export regularly to avoid data loss.**

## Features

- **One-command export** of all Antigravity conversations (active + archived)
- **Auto-discovery** of running LanguageServer instances
- **Dual output**: generates both original and redacted versions
- **Built-in privacy redaction**: API keys, passwords, emails, IPs, tokens, paths — all detected via regex + Shannon entropy analysis
- **Purely local** — no cloud upload, no external API calls

## Install

```bash
pip install -e .
# or
pip install git+https://github.com/Watermelon4000/antigravity-conversation-export.git
```

## Quick Start

```bash
# Export all conversations (original + redacted)
ag-export export -o ./my_export

# Show storage & connection info
ag-export info

# List all conversations
ag-export list
```

## Export Options

```bash
# Skip redaction (original only)
ag-export export -o ./output --no-redact

# Redacted only
ag-export export -o ./output --redact-only

# Exclude archived (implicit) conversations
ag-export export -o ./output --no-implicit

# Manual port/token (if auto-discovery fails)
ag-export export -o ./output --port 63400 --token <csrf_token>

# Extra usernames to anonymize
ag-export export -o ./output --redact-usernames "github_handle,discord_name"
```

## Output Structure

```
output/
├── original/              ← Raw conversations (Markdown + JSON)
├── redacted/              ← Privacy-safe version ([REDACTED] + hashed usernames)
└── export_report.txt      ← Export summary
```

## How It Works

1. Discovers running `language_server_macos` processes via `pgrep`
2. Extracts CSRF tokens from process args, finds listening ports via `lsof`
3. Connects to LanguageServer's gRPC-Web API over local HTTPS
4. Fetches conversation summaries and steps
5. Parses steps into structured messages (user / assistant / tool)
6. Formats as Markdown and JSON
7. Applies regex-based secret detection + username/path anonymization

## Antigravity Storage Limits

| Directory | Max Files | Content |
|-----------|-----------|---------|
| `~/.gemini/antigravity/conversations/` | 100 | Active conversations |
| `~/.gemini/antigravity/implicit/` | 100 | Archived (overflow) conversations |

When `conversations/` is full, the oldest conversation moves to `implicit/`. When `implicit/` is also full, the oldest archived conversation is **permanently deleted**. Use `--include-implicit` (enabled by default) to export both directories.

## Privacy Redaction

All redaction is **local regex + entropy analysis**, zero network calls:

| Type | Detection |
|------|-----------|
| API Keys | Pattern match (OpenAI `sk-`, Anthropic `sk-ant-`, HF `hf_`, GitHub `ghp_`, AWS `AKIA`, etc.) |
| Passwords | `PASSWORD=`, `SECRET=`, `TOKEN=`, env var patterns |
| Emails | Email regex with allowlist (noreply, example.com, etc.) |
| IP Addresses | IPv4 regex (excludes private/loopback) |
| JWT Tokens | `eyJ...` pattern matching |
| High-entropy strings | 40+ char strings in quotes with Shannon entropy > 3.5 |
| Usernames & paths | SHA256 hash replacement (`/Users/alice/` → `/user_a3b2c1d4/`) |

## Requirements

- Python >= 3.10
- Antigravity IDE must be running (for LanguageServer API access)
- macOS (Windows support partial)

## Credits

Inspired by [antigravity-history](https://github.com/neo1027144-creator/antigravity-history) and [dataclaw](https://github.com/peteromallet/dataclaw).

## License

MIT
