import base64
import hashlib
import os
import secrets
import sys
import time
import webbrowser
from datetime import datetime
from urllib.parse import urlencode

import click
import httpx
from rich import box
from rich.console import Console
from rich.table import Table

from insighta_cli.client import api_request
from insighta_cli.credentials import (
    clear_credentials,
    load_credentials,
    save_credentials,
)

console = Console()


# ── PKCE ──────────────────────────────────────────────────────────────────────

def _pkce() -> tuple[str, str, str]:
    """Returns (state, code_verifier, code_challenge). Challenge uses S256."""
    state = secrets.token_urlsafe(16)
    raw = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return state, verifier, challenge


# ── CLI root ──────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """Insighta Labs+ — demographic intelligence CLI."""
    pass


# ── AUTH ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--api-url", default=None, help="Backend API base URL")
def login(api_url):
    """Authenticate via GitHub OAuth (opens browser)."""
    base = (api_url or os.getenv("INSIGHTA_API_URL", "")).rstrip("/")
    if not base:
        base = click.prompt("Backend API URL (e.g. https://yourapp.up.railway.app)")
    base = base.rstrip("/")

    state, verifier, challenge = _pkce()

    # Build the URL that opens in the browser
    params = urlencode({
        "code_challenge": challenge,
        "state": state,
        "code_verifier": verifier,
    })
    auth_url = f"{base}/auth/github?{params}"

    console.print("\n[bold]Opening GitHub in your browser…[/bold]")
    console.print(f"[dim]If it doesn't open automatically:[/dim]\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Poll the backend for the token
    poll_url = f"{base}/auth/cli/token"
    console.print("[bold green]Waiting for GitHub authentication…[/bold green]")

    with console.status(""):
        for _ in range(240):  # 120 second timeout
            time.sleep(0.5)
            try:
                r = httpx.get(poll_url, params={"state": state}, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("access_token"):
                        save_credentials(
                            data["access_token"],
                            data["refresh_token"],
                            data["username"],
                            base,
                        )
                        console.print(f"\n[bold green]✓ Logged in as @{data['username']}[/bold green]\n")
                        return
            except Exception:
                pass

    console.print("[red]Login timed out (120s). Please try again.[/red]")
    sys.exit(1)


@cli.command()
def logout():
    """Revoke session and clear local credentials."""
    creds = load_credentials()
    if creds and creds.get("refresh_token"):
        try:
            httpx.post(
                f"{creds['api_url']}/auth/logout",
                json={"refresh_token": creds["refresh_token"]},
                headers={"Authorization": f"Bearer {creds['access_token']}"},
                timeout=5,
            )
        except Exception:
            pass
    clear_credentials()
    console.print("[green]Logged out.[/green]")


@cli.command()
def whoami():
    """Show currently authenticated user."""
    resp = api_request("GET", "/auth/me")
    if resp.status_code != 200:
        console.print(f"[red]{resp.json().get('detail', 'Error')}[/red]")
        return
    u = resp.json()["data"]
    t = Table(box=box.ROUNDED, show_header=False)
    t.add_column(style="dim")
    t.add_column()
    t.add_row("Username", f"@{u['username']}")
    t.add_row("Email", u.get("email") or "—")
    t.add_row("Role", u["role"])
    t.add_row("Active", "Yes" if u["is_active"] else "No")
    t.add_row("Joined", str(u.get("created_at", "—"))[:10])
    console.print(t)


# ── PROFILES ──────────────────────────────────────────────────────────────────

@cli.group()
def profiles():
    """Query and manage profiles."""
    pass


@profiles.command("list")
@click.option("--gender", help="male or female")
@click.option("--country", "country_id", help="ISO-2 code e.g. NG")
@click.option("--age-group", help="child | teenager | adult | senior")
@click.option("--min-age", type=int)
@click.option("--max-age", type=int)
@click.option("--min-gender-prob", type=float)
@click.option("--min-country-prob", type=float)
@click.option("--sort-by", type=click.Choice(["age", "created_at", "gender_probability"]))
@click.option("--order", type=click.Choice(["asc", "desc"]), default="asc")
@click.option("--page", type=int, default=1)
@click.option("--limit", type=int, default=10)
def profiles_list(gender, country_id, age_group, min_age, max_age,
                  min_gender_prob, min_country_prob, sort_by, order, page, limit):
    """List profiles with optional filters."""
    params = {"page": page, "limit": limit, "order": order}
    if gender: params["gender"] = gender
    if country_id: params["country_id"] = country_id.upper()
    if age_group: params["age_group"] = age_group
    if min_age is not None: params["min_age"] = min_age
    if max_age is not None: params["max_age"] = max_age
    if min_gender_prob is not None: params["min_gender_probability"] = min_gender_prob
    if min_country_prob is not None: params["min_country_probability"] = min_country_prob
    if sort_by: params["sort_by"] = sort_by

    with console.status("[bold green]Fetching profiles…"):
        resp = api_request("GET", "/api/profiles", params=params)
    _render_list(resp)


@profiles.command("search")
@click.argument("query")
@click.option("--page", type=int, default=1)
@click.option("--limit", type=int, default=10)
def profiles_search(query, page, limit):
    """Natural language search e.g. 'young males from nigeria'."""
    with console.status("[bold green]Searching…"):
        resp = api_request("GET", "/api/profiles/search",
                           params={"q": query, "page": page, "limit": limit})
    _render_list(resp)


@profiles.command("create")
@click.option("--name", required=True, help="Full name to create a profile for")
def profiles_create(name):
    """Create a new profile via external APIs. Admin only."""
    with console.status(f"[bold green]Creating profile for '{name}'…"):
        resp = api_request("POST", "/api/profiles", json={"name": name})
    if resp.status_code == 403:
        console.print("[red]Admin access required.[/red]")
        return
    if resp.status_code == 409:
        console.print("[yellow]Profile with this name already exists.[/yellow]")
        return
    if resp.status_code not in (200, 201):
        console.print(f"[red]Error: {resp.json().get('message', resp.text)}[/red]")
        return
    console.print("[bold green]✓ Profile created[/bold green]")
    _render_single(resp.json()["data"])


@profiles.command("export")
@click.option("--format", "fmt", default="csv", type=click.Choice(["csv"]))
@click.option("--gender")
@click.option("--country", "country_id")
@click.option("--age-group")
@click.option("--min-age", type=int)
@click.option("--max-age", type=int)
@click.option("--sort-by", type=click.Choice(["age", "created_at", "gender_probability"]))
@click.option("--order", type=click.Choice(["asc", "desc"]), default="asc")
def profiles_export(fmt, gender, country_id, age_group, min_age, max_age, sort_by, order):
    """Export profiles to a CSV file in the current directory."""
    params = {"format": fmt, "order": order}
    if gender: params["gender"] = gender
    if country_id: params["country_id"] = country_id.upper()
    if age_group: params["age_group"] = age_group
    if min_age is not None: params["min_age"] = min_age
    if max_age is not None: params["max_age"] = max_age
    if sort_by: params["sort_by"] = sort_by

    with console.status("[bold green]Exporting…"):
        resp = api_request("GET", "/api/profiles/export", params=params)
    if resp.status_code != 200:
        console.print(f"[red]Export failed: {resp.text}[/red]")
        return
    filename = f"profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, "wb") as f:
        f.write(resp.content)
    console.print(f"[green]✓ Saved:[/green] {filename}")


# ── Render helpers ─────────────────────────────────────────────────────────────

def _render_list(resp: httpx.Response):
    if resp.status_code in (400, 422):
        msg = resp.json()
        console.print(f"[red]{msg.get('detail') or msg.get('message', 'Error')}[/red]")
        return
    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}: {resp.text}[/red]")
        return
    body = resp.json()
    data = body.get("data", [])
    if not data:
        console.print("[yellow]No profiles found.[/yellow]")
        return
    t = Table(box=box.ROUNDED)
    t.add_column("Name", style="bold")
    t.add_column("Gender")
    t.add_column("Age", justify="right")
    t.add_column("Group")
    t.add_column("Country")
    t.add_column("G.Prob", justify="right")
    t.add_column("C.Prob", justify="right")
    for p in data:
        t.add_row(p["name"], p["gender"], str(p["age"]), p["age_group"],
                  f"{p['country_name']} ({p['country_id']})",
                  f"{p['gender_probability']:.2f}", f"{p['country_probability']:.2f}")
    console.print(t)
    console.print(f"[dim]Page {body.get('page',1)}/{body.get('total_pages',1)} — {body.get('total',0):,} total[/dim]")


def _render_single(p: dict):
    t = Table(box=box.ROUNDED, show_header=False)
    t.add_column(style="dim")
    t.add_column()
    for k, v in p.items():
        t.add_row(k, str(v))
    console.print(t)


if __name__ == "__main__":
    cli()
