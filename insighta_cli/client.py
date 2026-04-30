import sys
from typing import Any, Optional

import httpx
from rich.console import Console

from insighta_cli.credentials import (
    clear_credentials,
    load_credentials,
    save_credentials,
)

console = Console()


def _refresh_tokens(creds: dict) -> Optional[dict]:
    """Try to refresh access token. Returns updated creds or None."""
    try:
        resp = httpx.post(
            f"{creds['api_url']}/auth/refresh",
            json={"refresh_token": creds["refresh_token"]},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            new_creds = {
                **creds,
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
            }
            save_credentials(
                new_creds["access_token"],
                new_creds["refresh_token"],
                new_creds["username"],
                new_creds["api_url"],
            )
            return new_creds
    except Exception:
        pass
    return None


def api_request(
    method: str,
    path: str,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
    stream: bool = False,
) -> Any:
    """
    Make an authenticated API request.
    Auto-refreshes tokens on 401. Exits cleanly on auth failure.
    """
    creds = load_credentials()
    if not creds:
        console.print("[red]Not logged in. Run:[/red] insighta login")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {creds['access_token']}",
        "X-API-Version": "1",
    }
    url = f"{creds['api_url']}{path}"

    try:
        resp = httpx.request(method, url, headers=headers, params=params, json=json, timeout=30)

        if resp.status_code == 401:
            # Try refresh
            new_creds = _refresh_tokens(creds)
            if not new_creds:
                console.print("[red]Session expired. Please login again:[/red] insighta login")
                clear_credentials()
                sys.exit(1)
            headers["Authorization"] = f"Bearer {new_creds['access_token']}"
            resp = httpx.request(method, url, headers=headers, params=params, json=json, timeout=30)

        if resp.status_code == 429:
            console.print("[yellow]Rate limit exceeded. Please wait a moment.[/yellow]")
            sys.exit(1)

        return resp

    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {creds['api_url']}[/red]")
        sys.exit(1)
    except httpx.TimeoutException:
        console.print("[red]Request timed out.[/red]")
        sys.exit(1)
