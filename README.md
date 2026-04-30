# Insighta CLI

Command-line interface for Insighta Labs+. Authenticate via GitHub, query profiles, export data.

## Installation

```bash
git clone <cli-repo>
cd insighta-cli
pip install -e .
```

After install, `insighta` is available globally from any directory.
## Commands

### Auth

```bash
insighta login              # Authenticate via GitHub OAuth (opens browser)
insighta logout             # Revoke session and clear credentials
insighta whoami             # Show current user info
```

### Profiles

```bash
# List with filters
insighta profiles list
insighta profiles list --gender male
insighta profiles list --country NG --age-group adult
insighta profiles list --min-age 25 --max-age 40
insighta profiles list --sort-by age --order desc --page 2 --limit 20

# Natural language search
insighta profiles search "young males from nigeria"
insighta profiles search "adult females above 30"
insighta profiles search "seniors from ghana"

# Create profile (admin only)
insighta profiles create --name "Harriet Tubman"

# Export to CSV
insighta profiles export --format csv
insighta profiles export --format csv --gender male --country NG
```

## Token Handling

Credentials are saved at `~/.insighta/credentials.json` (chmod 600).

- On every API request, the access token is sent as `Authorization: Bearer <token>`
- The `X-API-Version: 1` header is included in all requests
- On **401 response**, the CLI automatically calls `POST /auth/refresh` with the stored refresh token and retries
- If refresh fails (token expired/revoked), credentials are cleared and the user is prompted to run `insighta login`

## OAuth Flow (CLI)

1. CLI generates PKCE values (`state`, `code_verifier`, `code_challenge` using S256)
2. Opens browser to `GET /auth/github?code_challenge=...&state=...&code_verifier=...`
3. Backend saves state + verifier, redirects to GitHub
4. User authenticates on GitHub
5. GitHub redirects to backend `/auth/github/callback?code=...&state=...`
6. Backend exchanges `code` + `code_verifier` with GitHub for an access token
7. Backend upserts user, issues JWT access token + refresh token
8. Backend stores tokens temporarily in DB keyed by `state`
9. CLI polls `GET /auth/cli/token?state=...` every 0.5s until tokens are returned
10. CLI saves tokens to `~/.insighta/credentials.json`

## Credential File Format

```json
{
  "access_token": "eyJ...",
  "refresh_token": "abc123...",
  "username": "your-github-username",
  "api_url": "https://yourapp.up.railway.app"
}
```
