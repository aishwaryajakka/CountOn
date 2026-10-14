"""Local-only bridge for the official Bee CLI.

This process invokes a fixed allowlist of CLI commands, keeps Bee authentication in
the Bee CLI, and sends only selected summaries/facts to CountOn.
"""

import argparse
import getpass
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


def _default_token_path() -> Path:
    try:
        return Path.home() / ".counton" / "bee-connector.json"
    except RuntimeError:
        return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".") / ".counton" / "bee-connector.json"


TOKEN_PATH = _default_token_path()
MAX_CLI_OUTPUT = 2_000_000


class BridgeError(RuntimeError):
    pass


def _run(*arguments: str, timeout: int = 30) -> str:
    binary = shutil.which("bee")
    if not binary:
        raise BridgeError("Bee CLI is not installed. Run: npm install -g @beeai/cli")
    try:
        result = subprocess.run(
            [binary, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as error:
        raise BridgeError("Bee CLI timed out") from error
    if result.returncode:
        raise BridgeError("Bee CLI is not authenticated or the request failed. Run: bee login")
    if len(result.stdout.encode()) > MAX_CLI_OUTPUT:
        raise BridgeError("Bee CLI response exceeded the safe import limit")
    return result.stdout


def detect() -> dict[str, Any]:
    if not shutil.which("bee"):
        return {"installed": False, "authenticated": False, "guidance": "npm install -g @beeai/cli"}
    version_raw = _run("version", "--json")
    try:
        version_data = json.loads(version_raw)
        version = str(version_data.get("version") or version_data.get("cli_version"))
    except (ValueError, AttributeError):
        version = version_raw.strip().split()[-1]
    try:
        profile = json.loads(_run("me", "--json"))
        if not isinstance(profile, dict):
            raise TypeError()
        # The documented profile shape does not promise a stable subject. Keep
        # the profile local and send only an opaque fingerprint for pairing.
        account_ref = str(profile.get("id") or profile.get("user_id") or hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest())
        authenticated = True
    except (BridgeError, ValueError, TypeError, AttributeError):
        account_ref, authenticated = "", False
    return {"installed": True, "authenticated": authenticated, "version": version, "account_ref": account_ref}


def _api_origin(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"} or not (parsed.scheme == "https" or local and parsed.scheme == "http"):
        raise BridgeError("CountOn API must be an HTTPS origin or a loopback HTTP origin")
    return value.rstrip("/")


def pair(api_url: str, pairing_code: str, token_path: Path = TOKEN_PATH) -> None:
    state = detect()
    if not state.get("authenticated"):
        raise BridgeError("Bee CLI requires authentication. Run: bee login")
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
        response = client.post(
            _api_origin(api_url) + "/api/v1/integrations/bee-cli/pair",
            json={"pairing_code": pairing_code, "cli_version": state["version"], "bee_account_ref": state["account_ref"]},
        )
    if response.status_code != 200:
        raise BridgeError("CountOn rejected the pairing code")
    payload = response.json()
    token_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    token_path.write_text(json.dumps({"api_url": _api_origin(api_url), "connector_token": payload["connector_token"], "connection_id": payload["connection_id"]}))
    token_path.chmod(0o600)


def _time(value: Any, fallback_ms: int) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_ms / 1000, timezone.utc).isoformat()


def normalize_changes(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Reduce `bee changed --json` output without retaining transcripts or audio."""
    meta_raw = data.get("meta")
    meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
    until = meta.get("until")
    fallback = int(until) if isinstance(until, (int, float)) else int(datetime.now(timezone.utc).timestamp() * 1000)
    candidates: list[dict[str, Any]] = []
    fields = {
        "facts": ("fact", "text"),
        "todos": ("todo", "text"),
        "conversations": ("conversation", "short_summary"),
        "journals": ("journal", "text"),
    }
    for collection, (category, text_field) in fields.items():
        rows = data.get(collection, [])
        if not isinstance(rows, list):
            raise BridgeError("Bee returned an unsupported change schema")
        for raw in rows:
            if not isinstance(raw, dict) or raw.get("id") is None or not isinstance(raw.get(text_field), str):
                continue
            summary = " ".join(raw[text_field].split())[:1000]
            if not summary:
                continue
            safe_version = hashlib.sha256(json.dumps({"id": raw["id"], "summary": summary, "completed": raw.get("completed"), "state": raw.get("state")}, sort_keys=True).encode()).hexdigest()[:32]
            item = {
                "external_id": f"{category}:{raw['id']}",
                "version": safe_version,
                "category": category,
                "summary": summary,
                "observed_at": _time(raw.get("updated_at") or raw.get("created_at") or raw.get("start_time"), int(fallback)),
                "confidence": 0.8 if category == "todo" else 0.7,
            }
            if category == "todo" and isinstance(raw.get("completed"), bool):
                item["completed"] = raw["completed"]
            candidates.append(item)
    cursor = meta.get("next_cursor")
    return candidates[:100], str(cursor) if cursor else None


def sync(token_path: Path = TOKEN_PATH) -> int:
    try:
        config = json.loads(token_path.read_text())
        token = config["connector_token"]
        api_url = _api_origin(config["api_url"])
    except (OSError, ValueError, KeyError) as error:
        raise BridgeError("Bee CLI is not paired with CountOn") from error
    cursor = config.get("checkpoint")
    arguments = ["changed", "--json"]
    if cursor:
        arguments[1:1] = ["--cursor", cursor]
    data = json.loads(_run(*arguments))
    candidates, next_cursor = normalize_changes(data)
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        response = client.post(api_url + "/api/v1/integrations/bee-cli/bridge/candidates", headers={"Authorization": f"Bearer {token}"}, json={"candidates": candidates, "next_cursor": next_cursor})
    if response.status_code != 200:
        raise BridgeError("CountOn rejected the Bee import preview")
    if next_cursor:
        config["checkpoint"] = next_cursor
        token_path.write_text(json.dumps(config))
        token_path.chmod(0o600)
    return int(response.json()["accepted"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Local CountOn bridge for the official Bee CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    pair_parser = commands.add_parser("pair")
    pair_parser.add_argument("--api", required=True)
    pair_parser.add_argument("--code-stdin", action="store_true", help="read the one-time code from a hidden prompt")
    commands.add_parser("sync")
    arguments = parser.parse_args()
    try:
        if arguments.command == "status":
            state = detect()
            print("Bee CLI installed" if state["installed"] else "Bee CLI not installed")
            print("Bee CLI authenticated" if state.get("authenticated") else "Bee CLI authentication required")
        elif arguments.command == "pair":
            if not arguments.code_stdin:
                raise BridgeError("Use --code-stdin so the pairing code is not exposed in the process list")
            pair(arguments.api, getpass.getpass("CountOn pairing code: "))
            print("Bee CLI paired with CountOn")
        else:
            print(f"Staged {sync()} Bee record(s) for review in CountOn")
        return 0
    except BridgeError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
