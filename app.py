"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK, same reasoning as every other connector this session -- the
user's own 1Password vaults/items/secrets live inside THEIR OWN
1Password account, accessed through a Connect server THEY deploy in
their own infrastructure.

WHY 1PASSWORD CONNECT SERVER + BEARER ACCESS TOKEN, NOT SERVICE ACCOUNTS
(confirmed against 1password.dev/connect/api-reference and
1password.dev/connect/concepts, 2026-08-29): 1Password offers two
automation mechanisms -- Connect Server (self-hosted REST API bridge,
Bearer access token, full CRUD on vaults/items/files) and Service
Accounts (simpler, hosted, but read-mostly and scoped per-account, no
self-hosted REST surface of its own). Connect Server is the one with a
real documented REST API surface (vaults/items/files/API-activity) that
matches this connector's read/write ambitions, so it's the target this
release. Service Accounts could be a lighter-weight v2 alternative flagged
in PREPARATION.md.

WHY EACH CONNECTION STORES A CONNECT SERVER URL + ACCESS TOKEN, SAME
SHAPE AS CYBERARK/ANSIBLE CONNECTOR'S base_url + token pattern -- a
Connect server is scoped to specific vaults at deploy time (which vaults
it can reach is fixed by whoever deployed it), so there is no "list every
vault in the account" -- only "list vaults this token can reach".
"""
from __future__ import annotations

from imperal_sdk import ChatExtension, Extension

ext = Extension(
    "1password-connector",
    version="0.1.0",
    display_name="1Password",
    icon="icon.svg",
    capabilities=["1password:read", "1password:write"],
    description=(
        "Connect your own 1Password Connect Server (self-hosted, Bearer access token) to read and manage "
        "vaults, items (logins, passwords, secure notes, API credentials), and file attachments -- full "
        "read/write plus value-add vault health and stale-item reports. Item secrets are never logged."
    ),
)

chat = ChatExtension(ext)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one Connect server is stored, same shape as Buildium's/Cin7
    Core's health_check."""
    import json as _json
    raw = await ctx.secrets.get("onepassword_connections")
    try:
        count = len(_json.loads(raw)) if raw else 0
    except Exception:
        count = 0
    return {
        "healthy": True,
        "detail": (
            f"{count} 1Password Connect server(s) connected." if count
            else "Not connected yet -- run connect_onepassword."
        ),
    }
