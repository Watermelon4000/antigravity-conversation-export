"""
LanguageServer API client.
Calls Antigravity's local gRPC-Web API over HTTPS (self-signed cert).
"""

from typing import Any, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_PATH = "exa.language_server_pb.LanguageServerService"


def call_api(
    port: int,
    csrf_token: str,
    method: str,
    params: Optional[dict] = None,
    timeout: int = 15,
) -> Optional[dict]:
    """Call LanguageServer gRPC-Web API."""
    url = f"https://localhost:{port}/{BASE_PATH}/{method}"
    headers = {
        "Content-Type": "application/json",
        "Connect-Protocol-Version": "1",
        "X-Codeium-Csrf-Token": csrf_token,
    }
    try:
        resp = requests.post(
            url, headers=headers, json=params or {}, verify=False, timeout=timeout
        )
        if resp.status_code == 200:
            return resp.json()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass
    except Exception:
        pass
    return None


def get_all_trajectories(port: int, csrf: str) -> dict[str, Any]:
    """Get all conversation summaries."""
    result = call_api(port, csrf, "GetAllCascadeTrajectories", timeout=3)
    if not result:
        return {}
    return result.get("trajectorySummaries", {})


def get_trajectory_steps(
    port: int, csrf: str, cascade_id: str, step_count: int = 1000
) -> list[dict]:
    """Get all steps for a conversation."""
    result = call_api(
        port, csrf, "GetCascadeTrajectorySteps",
        {"cascadeId": cascade_id, "startIndex": 0, "endIndex": step_count + 10},
        timeout=30,
    )
    if not result:
        return []
    return result.get("steps", result.get("messages", []))
