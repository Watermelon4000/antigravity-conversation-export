"""
Step parser — parse raw LanguageServer API steps into structured messages.

Three-level field strategy:
  default:  response, userResponse, basic tool calls
  thinking: + thinking, timestamp, exitCode, cwd, stopReason
  full:     + diff, combinedOutput, searchSummary, model, thinkingDuration
"""

from typing import Optional


class FieldLevel:
    DEFAULT = "default"
    THINKING = "thinking"
    FULL = "full"


def parse_steps(
    steps: list[dict],
    level: str = FieldLevel.DEFAULT,
) -> list[dict]:
    """Parse raw steps into structured messages."""
    include_thinking = level in (FieldLevel.THINKING, FieldLevel.FULL)
    include_full = level == FieldLevel.FULL

    messages = []
    for step in steps:
        step_type = step.get("type", "")
        metadata = step.get("metadata", {})
        timestamp = metadata.get("createdAt") if include_thinking else None

        msg = _parse_step(step, step_type, include_thinking, include_full)
        if msg is None:
            continue
        if timestamp:
            msg["timestamp"] = timestamp
        messages.append(msg)

    return messages


_DIFF_PREFIX = {
    "UNIFIED_DIFF_LINE_TYPE_INSERT": "+",
    "UNIFIED_DIFF_LINE_TYPE_DELETE": "-",
    "UNIFIED_DIFF_LINE_TYPE_CONTEXT": " ",
}


def _normalize_diff(diff) -> str:
    if isinstance(diff, str):
        return diff
    if isinstance(diff, dict):
        lines_data = diff.get("unifiedDiff", {}).get("lines", [])
        if not lines_data:
            return str(diff)
        parts = []
        for line in lines_data:
            text = line.get("text", "")
            prefix = _DIFF_PREFIX.get(line.get("type", ""), " ")
            parts.append(f"{prefix}{text}")
        return "\n".join(parts)
    return str(diff)


def _parse_step(step, step_type, include_thinking, include_full) -> Optional[dict]:
    if step_type == "CORTEX_STEP_TYPE_USER_INPUT":
        ui = step.get("userInput", {})
        content = ui.get("userResponse", "")
        if not content:
            return None
        msg = {"role": "user", "content": content}
        if include_full:
            state = ui.get("activeUserState", {})
            active_doc = state.get("activeDocument", {})
            if active_doc.get("absoluteUri"):
                msg["active_file"] = active_doc["absoluteUri"]
        return msg

    if step_type == "CORTEX_STEP_TYPE_PLANNER_RESPONSE":
        pr = step.get("plannerResponse", {})
        content = pr.get("modifiedResponse") or pr.get("response", "")
        if not content:
            return None
        msg = {"role": "assistant", "content": content}
        if include_thinking:
            thinking = pr.get("thinking")
            if thinking:
                msg["thinking"] = thinking
            stop_reason = pr.get("stopReason")
            if stop_reason:
                msg["stop_reason"] = stop_reason
        if include_full:
            metadata = step.get("metadata", {})
            model = metadata.get("generatorModel")
            if model:
                msg["model"] = model
            td = pr.get("thinkingDuration")
            if td:
                msg["thinking_duration"] = td
        return msg

    if step_type == "CORTEX_STEP_TYPE_CODE_ACTION":
        ca = step.get("codeAction", {})
        description = ca.get("description", "")
        file_path = ""
        ar = ca.get("actionResult", {})
        edit = ar.get("edit", {})
        if edit.get("absoluteUri"):
            file_path = edit["absoluteUri"]
        elif ca.get("actionSpec", {}).get("createFile", {}).get("path"):
            file_path = ca["actionSpec"]["createFile"]["path"]
        summary = f"[Code Edit] {file_path}" if file_path else "[Code Edit]"
        if description:
            summary += f"\n{description}"
        msg = {"role": "tool", "tool_name": "code_edit", "content": summary}
        if file_path:
            msg["file_path"] = file_path
        if include_full:
            diff = edit.get("diff")
            if diff:
                msg["diff"] = _normalize_diff(diff)
        return msg

    if step_type == "CORTEX_STEP_TYPE_RUN_COMMAND":
        rc = step.get("runCommand", {})
        command = rc.get("commandLine", rc.get("command", ""))
        if not command:
            return None
        msg = {"role": "tool", "tool_name": "run_command", "content": command}
        if include_thinking:
            cwd = rc.get("cwd")
            if cwd:
                msg["cwd"] = cwd
            exit_code = rc.get("exitCode")
            if exit_code is not None:
                msg["exit_code"] = exit_code
        if include_full:
            output = rc.get("combinedOutput", {}).get("full")
            if output:
                msg["output"] = output
        return msg

    if step_type == "CORTEX_STEP_TYPE_VIEW_FILE":
        vf = step.get("viewFile", {})
        path = vf.get("absolutePathUri", vf.get("filePath", vf.get("path", "")))
        if not path:
            return None
        msg = {"role": "tool", "tool_name": "view_file", "content": path}
        if include_thinking:
            if vf.get("numLines"):
                msg["num_lines"] = vf["numLines"]
            if vf.get("numBytes"):
                msg["num_bytes"] = vf["numBytes"]
        return msg

    if step_type == "CORTEX_STEP_TYPE_FIND":
        find = step.get("find", {})
        return {"role": "tool", "tool_name": "find", "content": find.get("query", "[File Search]")}

    if step_type == "CORTEX_STEP_TYPE_LIST_DIRECTORY":
        ld = step.get("listDirectory", {})
        path = ld.get("directoryPath", ld.get("path", ""))
        return {"role": "tool", "tool_name": "list_dir", "content": path or "[List Directory]"}

    if step_type == "CORTEX_STEP_TYPE_SEARCH_WEB":
        sw = step.get("searchWeb", {})
        query = sw.get("query", "")
        msg = {"role": "tool", "tool_name": "search_web", "content": query or "[Web Search]"}
        if include_full:
            s = sw.get("summary")
            if s:
                msg["search_summary"] = s
        return msg

    if step_type == "CORTEX_STEP_TYPE_READ_URL_CONTENT":
        ru = step.get("readUrlContent", {})
        return {"role": "tool", "tool_name": "read_url", "content": ru.get("url", "[Read URL]")}

    if step_type == "CORTEX_STEP_TYPE_COMMAND_STATUS":
        return {"role": "tool", "tool_name": "command_status", "content": "[Check Command Status]"}

    return None
