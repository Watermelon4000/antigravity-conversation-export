"""
Process discovery — auto-detect running Antigravity LanguageServer instances.
Finds language_server_macos processes, extracts CSRF tokens from cmdline args,
and discovers listening ports via lsof.
"""

import platform
import re
import subprocess
from typing import Optional


def discover_language_servers() -> list[dict]:
    """Discover all running language_server processes.
    Returns: [{"pid": int, "csrf": str, "cmd": str}, ...]
    """
    system = platform.system()
    if system == "Darwin":
        return _discover_macos()
    elif system == "Windows":
        return _discover_windows()
    else:
        return []


def _discover_macos() -> list[dict]:
    servers = []
    try:
        result = subprocess.run(
            ["pgrep", "-f", "language_server_macos"],
            capture_output=True, text=True
        )
        for pid in result.stdout.strip().split("\n"):
            if not pid.strip():
                continue
            ps_result = subprocess.run(
                ["ps", "-p", pid, "-o", "args="],
                capture_output=True, text=True
            )
            cmd = ps_result.stdout.strip()
            csrf = ""
            if m := re.search(r"--csrf_token\s+(\S+)", cmd):
                csrf = m.group(1)
            servers.append({"pid": int(pid), "csrf": csrf, "cmd": cmd})
    except Exception:
        pass
    return servers


def _discover_windows() -> list[dict]:
    import json as json_mod
    servers = []
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'language_server*' } | "
             "Select-Object ProcessId, CommandLine | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0 or not result.stdout.strip():
            return servers
        data = json_mod.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        for proc in data:
            cmd = proc.get("CommandLine", "")
            pid = proc.get("ProcessId")
            csrf = ""
            if m := re.search(r"--csrf_token\s+(\S+)", cmd):
                csrf = m.group(1)
            servers.append({"pid": pid, "csrf": csrf, "cmd": cmd})
    except Exception:
        pass
    return servers


def find_ports(pid: int) -> list[int]:
    """Find TCP ports a given process is listening on."""
    if platform.system() == "Windows":
        return _find_ports_windows(pid)
    return _find_ports_macos(pid)


def _find_ports_macos(pid: int) -> list[int]:
    ports = []
    try:
        result = subprocess.run(
            ["lsof", "-p", str(pid), "-i", "TCP", "-P", "-n"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            # Only match lines from the actual language_server process
            if "LISTEN" in line and "language_" in line:
                if m := re.search(r":(\d+)\s+\(LISTEN\)", line):
                    ports.append(int(m.group(1)))
    except Exception:
        pass
    return ports


def _find_ports_windows(pid: int) -> list[int]:
    ports = []
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            if "LISTENING" in line and str(pid) in line:
                if m := re.search(r"127\.0\.0\.1:(\d+)", line):
                    ports.append(int(m.group(1)))
    except Exception:
        pass
    return ports


def find_working_endpoint(
    servers: list[dict],
    manual_port: Optional[int] = None,
    manual_token: Optional[str] = None,
) -> Optional[dict]:
    """Find the first working LanguageServer endpoint.
    Returns: {"port": int, "csrf": str, "pid": int} or None
    """
    if manual_port and manual_token:
        return {"port": manual_port, "csrf": manual_token, "pid": 0}

    from ag_export.api import call_api

    for srv in servers:
        ports = find_ports(srv["pid"])
        for port in ports:
            result = call_api(port, srv["csrf"], "GetAllCascadeTrajectories", timeout=3)
            if result is not None:
                return {"port": port, "csrf": srv["csrf"], "pid": srv["pid"]}

    return None
