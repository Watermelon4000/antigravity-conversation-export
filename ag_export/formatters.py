"""
Formatted output — Markdown / JSON.
"""

import json
import os
import re
from datetime import datetime


def format_markdown(
    title: str,
    cascade_id: str,
    metadata: dict,
    messages: list[dict],
) -> str:
    """Format a conversation as a Markdown string."""
    lines = [
        f"# {title}", "",
        f"- **Cascade ID**: `{cascade_id}`",
        f"- **Steps**: {metadata.get('stepCount', '?')}",
        f"- **Status**: {metadata.get('status', '?')}",
        f"- **Created**: {metadata.get('createdTime', '?')}",
        f"- **Last Modified**: {metadata.get('lastModifiedTime', '?')}",
    ]
    workspaces = metadata.get("workspaces", [])
    if not workspaces:
        workspaces = metadata.get("trajectoryMetadata", {}).get("workspaces", [])
    if workspaces:
        ws_uris = [w.get("workspaceFolderAbsoluteUri", "") for w in workspaces if w.get("workspaceFolderAbsoluteUri")]
        if ws_uris:
            lines.append(f"- **Workspace**: {', '.join(ws_uris)}")
    lines.extend([
        f"- **Exported**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "", "---", ""
    ])
    for msg in messages:
        lines.extend(_format_message_md(msg))
    return "\n".join(lines)


def _format_message_md(msg: dict) -> list[str]:
    role = msg.get("role", "")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")
    ts_suffix = f"  `{timestamp[:19]}`" if timestamp else ""
    lines = []

    if role == "user":
        lines.append(f"## 🧑 User{ts_suffix}")
        lines.append(content)
        lines.append("")

    elif role == "assistant":
        lines.append(f"## 🤖 Assistant{ts_suffix}")
        thinking = msg.get("thinking")
        if thinking:
            lines.append("<details><summary>💭 Thinking</summary>")
            lines.append("")
            lines.append(thinking)
            lines.append("")
            lines.append("</details>")
            lines.append("")
        lines.append(content)
        extras = []
        if msg.get("model"):
            extras.append(f"Model: `{msg['model']}`")
        if msg.get("stop_reason"):
            extras.append(f"Stop: `{msg['stop_reason']}`")
        if msg.get("thinking_duration"):
            extras.append(f"Think: `{msg['thinking_duration']}`")
        if extras:
            lines.append("")
            lines.append(f"*{' | '.join(extras)}*")
        lines.append("")

    elif role == "tool":
        tool_name = msg.get("tool_name", "unknown")
        lines.append(f"### 🔧 Tool: `{tool_name}`{ts_suffix}")

        if tool_name == "code_edit":
            lines.append(content)
            diff = msg.get("diff")
            if diff:
                lines.append("")
                lines.append("```diff")
                if len(diff) > 3000:
                    lines.append(diff[:3000])
                    lines.append(f"... (truncated, {len(diff)} chars total)")
                else:
                    lines.append(diff)
                lines.append("```")

        elif tool_name == "run_command":
            cwd = msg.get("cwd", "")
            exit_code = msg.get("exit_code")
            lines.append("```bash")
            lines.append(content)
            lines.append("```")
            meta_parts = []
            if cwd:
                meta_parts.append(f"in `{cwd}`")
            if exit_code is not None:
                meta_parts.append(f"exit {exit_code}")
            if meta_parts:
                lines.append(f"*{' → '.join(meta_parts)}*")
            output = msg.get("output")
            if output:
                lines.append("")
                lines.append("<details><summary>📤 Output</summary>")
                lines.append("")
                lines.append("```")
                if len(output) > 5000:
                    lines.append(output[:5000])
                    lines.append(f"... (truncated, {len(output)} chars total)")
                else:
                    lines.append(output)
                lines.append("```")
                lines.append("")
                lines.append("</details>")

        elif tool_name == "search_web":
            lines.append(f"Query: {content}")
            ss = msg.get("search_summary")
            if ss:
                lines.append("")
                lines.append("<details><summary>🔍 Search Results</summary>")
                lines.append("")
                lines.append(ss)
                lines.append("")
                lines.append("</details>")

        elif tool_name == "view_file":
            num_lines = msg.get("num_lines")
            num_bytes = msg.get("num_bytes")
            size_parts = []
            if num_lines:
                size_parts.append(f"{num_lines} lines")
            if num_bytes:
                size_parts.append(f"{num_bytes} bytes")
            size_info = f" ({', '.join(size_parts)})" if size_parts else ""
            lines.append(f"`{content}`{size_info}")

        else:
            if content:
                lines.append(f"`{content[:500]}`")

        lines.append("")

    return lines


def format_json(conversations: list[dict]) -> str:
    return json.dumps(conversations, indent=2, ensure_ascii=False)


def build_conversation_record(
    cascade_id: str,
    title: str,
    metadata: dict,
    messages: list[dict],
) -> dict:
    record = {
        "cascade_id": cascade_id,
        "title": title,
        "step_count": metadata.get("stepCount", 0),
        "created_time": metadata.get("createdTime", ""),
        "last_modified_time": metadata.get("lastModifiedTime", ""),
        "messages": messages,
    }
    workspaces = metadata.get("workspaces", [])
    if workspaces:
        ws_uris = [w.get("workspaceFolderAbsoluteUri", "")
                    for w in workspaces if w.get("workspaceFolderAbsoluteUri")]
        if ws_uris:
            record["workspaces"] = ws_uris
    return record


def safe_filename(title: str, max_len: int = 60) -> str:
    return re.sub(r'[^\w\s\-]', '_', title)[:max_len].strip()


def write_conversation(
    content: str, title: str, output_dir: str, extension: str = ".md",
) -> str:
    base = safe_filename(title)
    filepath = os.path.join(output_dir, base + extension)
    counter = 2
    while os.path.exists(filepath):
        filepath = os.path.join(output_dir, f"{base}_{counter}{extension}")
        counter += 1
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath
