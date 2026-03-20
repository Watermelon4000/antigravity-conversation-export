---
description: Export Antigravity conversation history locally with privacy redaction
---

# Export Antigravity Conversations

// turbo-all

## Steps

1. Install ag-export (skip if already installed):
```bash
pip install -e /path/to/ag-export
```

2. Show current storage info:
```bash
ag-export info
```

3. Export all conversations (original + redacted):
```bash
ag-export export -o ~/Desktop/Projects/ai_conversation_history/antigravity_export
```

4. If export hangs at "probing ports", manually specify port and token:
```bash
# Find port and token
PID=$(pgrep -f language_server_macos | head -1)
CSRF=$(ps -p $PID -o args= | grep -oE '\-\-csrf_token [^ ]+' | awk '{print $2}')
PORT=$(lsof -p $PID -i TCP -P -n 2>/dev/null | grep "language_" | grep LISTEN | head -1 | grep -oE ':[0-9]+' | head -1 | tr -d ':')

ag-export export -o ~/Desktop/Projects/ai_conversation_history/antigravity_export --port $PORT --token $CSRF
```
