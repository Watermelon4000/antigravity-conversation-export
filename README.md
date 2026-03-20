# ag-export

Export Antigravity AI conversations locally with built-in privacy redaction.

## Features

- **One-command export** of all Antigravity conversations (active + archived)
- **Auto-discovery** of running LanguageServer instances
- **Dual output**: generates both original and redacted versions
- **Built-in privacy redaction**: API keys, passwords, emails, IPs, tokens, paths — all detected via regex + Shannon entropy analysis
- **Purely local** — no cloud upload, no external API calls

## Install

```bash
pip install -e .
```

## Usage

```bash
# Export all conversations (original + redacted)
ag-export export -o ./my_export

# Show storage & connection info
ag-export info

# List all conversations
ag-export list
```

### Export Options

```bash
# Skip redaction (original only)
ag-export export -o ./output --no-redact

# Redacted only
ag-export export -o ./output --redact-only

# Exclude archived conversations
ag-export export -o ./output --no-implicit

# Manual port/token (if auto-discovery fails)
ag-export export -o ./output --port 63400 --token <csrf_token>

# Extra usernames to anonymize
ag-export export -o ./output --redact-usernames "github_handle,discord_name"
```

### Output Structure

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
5. Parses steps into structured messages (user/assistant/tool)
6. Formats as Markdown and JSON
7. Applies regex-based secret detection + username/path anonymization

## Privacy Redaction

All redaction is **local regex + entropy analysis**, no AI/API calls:

| Type | Detection |
|------|-----------|
| API Keys | Pattern match (OpenAI, Anthropic, HF, GitHub, AWS, etc.) |
| Passwords | `PASSWORD=`, `SECRET=`, env var patterns |
| Emails | Email regex with allowlist (noreply, example.com, etc.) |
| IP Addresses | IPv4 regex (excludes private/loopback) |
| JWT Tokens | `eyJ...` pattern |
| High-entropy strings | 40+ char strings with Shannon entropy > 3.5 |
| Usernames/paths | SHA256 hash replacement |

## Requirements

- Python >= 3.10
- Antigravity IDE running (for LanguageServer API access)
- macOS (Windows support partial)

## License

MIT
