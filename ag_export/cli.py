"""
CLI entry point for ag-export.

Commands:
  export  — Export all Antigravity conversations (original + redacted)
  list    — List all conversations
  info    — Show connection and storage info
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import track

from ag_export.api import get_all_trajectories, get_trajectory_steps
from ag_export.discovery import discover_language_servers, find_working_endpoint
from ag_export.formatters import (
    build_conversation_record,
    format_json,
    format_markdown,
    safe_filename,
    write_conversation,
)
from ag_export.parser import FieldLevel, parse_steps
from ag_export.redactor import Anonymizer, redact_full

app = typer.Typer(
    name="ag-export",
    help="Export Antigravity AI conversations locally with built-in privacy redaction.",
    no_args_is_help=True,
)
console = Console()

AG_DIR = Path.home() / ".gemini" / "antigravity"
CONVERSATIONS_DIR = AG_DIR / "conversations"
IMPLICIT_DIR = AG_DIR / "implicit"


def _connect(
    port: Optional[int] = None, token: Optional[str] = None
) -> dict:
    """Discover and connect to a running LanguageServer."""
    if port and token:
        console.print(f"  Using manual endpoint: port={port}")
        return {"port": port, "csrf": token, "pid": 0}

    console.print("  🔍 Discovering LanguageServer instances...")
    servers = discover_language_servers()
    if not servers:
        console.print("  [red]✗ No running Antigravity instances found.[/red]")
        console.print("    Please open Antigravity IDE and try again.")
        raise typer.Exit(1)

    console.print(f"  Found {len(servers)} process(es), probing ports...")
    endpoint = find_working_endpoint(servers, port, token)
    if not endpoint:
        console.print("  [red]✗ Could not connect to any LanguageServer.[/red]")
        console.print("    Try specifying --port and --token manually.")
        raise typer.Exit(1)

    console.print(f"  [green]✓ Connected[/green] (PID {endpoint['pid']}, port {endpoint['port']})")
    return endpoint


def _setup_implicit_symlinks() -> list[Path]:
    """Symlink implicit (archived) conversations into conversations/ dir."""
    if not IMPLICIT_DIR.exists():
        return []
    created = []
    for pb_file in IMPLICIT_DIR.glob("*.pb"):
        target = CONVERSATIONS_DIR / pb_file.name
        if not target.exists():
            try:
                target.symlink_to(pb_file)
                created.append(target)
            except OSError:
                pass
    return created


def _cleanup_symlinks(symlinks: list[Path]):
    """Remove symlinks we created."""
    for link in symlinks:
        try:
            if link.is_symlink():
                link.unlink()
        except OSError:
            pass


def _gather_conversations(port: int, csrf: str) -> list[dict]:
    """Fetch all conversation summaries from the API and physical files."""
    summaries = get_all_trajectories(port, csrf) or {}

    all_ids = set(summaries.keys())
    for d in [CONVERSATIONS_DIR, IMPLICIT_DIR]:
        if d.exists():
            for pb in d.glob("*.pb"):
                all_ids.add(pb.stem)

    conversations = []
    for cascade_id in all_ids:
        meta = summaries.get(cascade_id, {})
        title = meta.get("title", "")
        # Use 10000 as a safe default for step_count if unknown
        step_count = meta.get("stepCount", 10000)

        if not meta.get("lastModifiedTime"):
            pb_path = CONVERSATIONS_DIR / f"{cascade_id}.pb"
            if not pb_path.exists():
                pb_path = IMPLICIT_DIR / f"{cascade_id}.pb"
            if pb_path.exists():
                try:
                    mtime = pb_path.stat().st_mtime
                    meta["lastModifiedTime"] = datetime.fromtimestamp(mtime).isoformat() + "Z"
                except OSError:
                    pass

        conversations.append({
            "cascade_id": cascade_id,
            "title": title,
            "step_count": step_count,
            "metadata": meta,
        })

    conversations.sort(key=lambda c: c["metadata"].get("lastModifiedTime", ""), reverse=True)
    return conversations


@app.command()
def export(
    output: str = typer.Option(..., "-o", "--output", help="Output directory"),
    include_implicit: bool = typer.Option(
        True, "--include-implicit/--no-implicit",
        help="Include archived (implicit) conversations"
    ),
    redact: bool = typer.Option(
        True, "--redact/--no-redact",
        help="Generate redacted version"
    ),
    redact_only: bool = typer.Option(
        False, "--redact-only",
        help="Only generate redacted version"
    ),
    level: str = typer.Option(
        "full", "--level", "-l",
        help="Detail level: default/thinking/full"
    ),
    format: str = typer.Option(
        "all", "-f", "--format",
        help="Output format: md/json/all"
    ),
    port: Optional[int] = typer.Option(None, "--port", help="Manual LanguageServer port"),
    token: Optional[str] = typer.Option(None, "--token", help="Manual CSRF token"),
    extra_usernames: Optional[str] = typer.Option(
        None, "--redact-usernames",
        help="Comma-separated extra usernames to anonymize"
    ),
):
    """Export all Antigravity conversations with optional privacy redaction."""
    console.print("\n[bold]ag-export[/bold] — Antigravity Conversation Exporter\n")

    # 1. Connect
    endpoint = _connect(port, token)

    # 2. Symlink implicit conversations
    symlinks = []
    if include_implicit:
        symlinks = _setup_implicit_symlinks()
        if symlinks:
            console.print(f"  📦 Linked {len(symlinks)} archived conversations")

    try:
        # 3. Gather conversation list
        console.print("  📋 Fetching conversation list...")
        conversations = _gather_conversations(endpoint["port"], endpoint["csrf"])
        if not conversations:
            console.print("  [yellow]No conversations found.[/yellow]")
            raise typer.Exit(0)
        
        indexed = [c for c in conversations if c["title"]]
        unindexed = [c for c in conversations if not c["title"]]
        console.print(f"  Found {len(conversations)} conversations "
                      f"({len(indexed)} indexed, {len(unindexed)} unindexed)\n")

        # 4. Setup output dirs
        original_dir = os.path.join(output, "original")
        redacted_dir = os.path.join(output, "redacted")

        if not redact_only:
            os.makedirs(original_dir, exist_ok=True)
        if redact or redact_only:
            os.makedirs(redacted_dir, exist_ok=True)

        # 5. Setup anonymizer
        extra = extra_usernames.split(",") if extra_usernames else None
        anonymizer = Anonymizer(extra_usernames=extra)

        # 6. Export each conversation
        total_messages = 0
        exported = 0
        failed = 0
        all_records = []

        for conv in track(conversations, description="  Exporting..."):
            cascade_id = conv["cascade_id"]
            step_count = conv["step_count"]
            title = conv["title"] or f"[unindexed] {cascade_id[:8]}..."

            try:
                steps = get_trajectory_steps(
                    endpoint["port"], endpoint["csrf"],
                    cascade_id, step_count
                )
                messages = parse_steps(steps, level=level)
                total_messages += len(messages)

                if not messages:
                    # Still count as exported, just empty
                    exported += 1
                    continue

                metadata = conv["metadata"]

                # Build JSON record
                record = build_conversation_record(cascade_id, title, metadata, messages)
                all_records.append(record)

                # Write original
                if not redact_only:
                    if format in ("md", "all"):
                        md = format_markdown(title, cascade_id, metadata, messages)
                        write_conversation(md, title, original_dir, ".md")
                    if format in ("json", "all"):
                        pass  # JSON written as a single file at the end

                # Write redacted
                if redact or redact_only:
                    if format in ("md", "all"):
                        md = format_markdown(title, cascade_id, metadata, messages)
                        redacted_md, _ = redact_full(md, anonymizer)
                        write_conversation(redacted_md, title, redacted_dir, ".md")

                exported += 1

            except Exception as e:
                failed += 1
                console.print(f"  [red]✗ Failed: {title} — {e}[/red]")

        # 7. Write JSON files
        if format in ("json", "all") and all_records:
            if not redact_only:
                json_path = os.path.join(original_dir, "conversations_export.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    f.write(format_json(all_records))

            if redact or redact_only:
                json_str = format_json(all_records)
                redacted_json, _ = redact_full(json_str, anonymizer)
                json_path = os.path.join(redacted_dir, "conversations_export.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    f.write(redacted_json)

        # 8. Write export report
        report = _build_report(exported, failed, total_messages, len(conversations), output)
        report_path = os.path.join(output, "export_report.txt")
        with open(report_path, "w") as f:
            f.write(report)

        # 9. Summary
        console.print(f"\n  [green]✓ Done![/green]")
        console.print(f"    Exported: {exported} conversations, {total_messages} messages")
        if failed:
            console.print(f"    Failed:   {failed}")
        console.print(f"    Output:   {output}/")
        if not redact_only:
            console.print(f"              ├── original/   (raw)")
        if redact or redact_only:
            console.print(f"              ├── redacted/   (privacy-safe)")
        console.print(f"              └── export_report.txt\n")

    finally:
        _cleanup_symlinks(symlinks)


@app.command(name="list")
def list_conversations(
    port: Optional[int] = typer.Option(None, "--port", help="Manual LanguageServer port"),
    token: Optional[str] = typer.Option(None, "--token", help="Manual CSRF token"),
    include_implicit: bool = typer.Option(
        True, "--include-implicit/--no-implicit",
        help="Include archived conversations"
    ),
):
    """List all Antigravity conversations."""
    console.print("\n[bold]ag-export list[/bold]\n")
    endpoint = _connect(port, token)

    symlinks = []
    if include_implicit:
        symlinks = _setup_implicit_symlinks()

    try:
        conversations = _gather_conversations(endpoint["port"], endpoint["csrf"])
        console.print(f"\n  Total: {len(conversations)} conversations\n")
        for i, conv in enumerate(conversations, 1):
            title = conv["title"] or f"[unindexed] {conv['cascade_id'][:8]}..."
            steps = conv["step_count"]
            console.print(f"  {i:4d}. {title}")
            console.print(f"        Steps: {steps}  |  ID: {conv['cascade_id'][:12]}...")
    finally:
        _cleanup_symlinks(symlinks)


@app.command()
def info():
    """Show Antigravity storage and LanguageServer info."""
    console.print("\n[bold]ag-export info[/bold]\n")

    # Storage info
    conv_count = len(list(CONVERSATIONS_DIR.glob("*.pb"))) if CONVERSATIONS_DIR.exists() else 0
    impl_count = len(list(IMPLICIT_DIR.glob("*.pb"))) if IMPLICIT_DIR.exists() else 0

    console.print(f"  📁 Conversations dir: {CONVERSATIONS_DIR}")
    console.print(f"     Active:   {conv_count} .pb files")
    console.print(f"  📁 Implicit dir:      {IMPLICIT_DIR}")
    console.print(f"     Archived: {impl_count} .pb files")
    console.print(f"     Total:    {conv_count + impl_count} conversations\n")

    # LanguageServer info
    servers = discover_language_servers()
    if servers:
        console.print(f"  🖥️  LanguageServer processes: {len(servers)}")
        for srv in servers:
            console.print(f"     PID {srv['pid']}: token={srv['csrf'][:12]}...")
    else:
        console.print("  [yellow]⚠ No running LanguageServer instances found[/yellow]")

    console.print()


def _build_report(
    exported: int, failed: int, messages: int, total: int, output: str
) -> str:
    lines = [
        "=" * 60,
        "  ag-export — Export Report",
        "=" * 60,
        "",
        f"  Date:           {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Output:         {output}",
        f"  Total found:    {total}",
        f"  Exported:       {exported}",
        f"  Failed:         {failed}",
        f"  Messages:       {messages}",
        "",
        "=" * 60,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    app()
