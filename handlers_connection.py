"""Connection lifecycle: connect (verify against /v1/vaults), list, disconnect.

Same "secrets-store list of dicts" shape as every other BYOK connector
this session's handlers_connection.py.
"""
from __future__ import annotations

import json
import uuid

from imperal_sdk import ActionResult

import onepassword_client as oc
from app import chat
from schemas import (
    ConnectOnePasswordParams, ConnectOnePasswordResult,
    DisconnectOnePasswordParams, DeleteResult,
    OnePasswordConnection, ConnectionList, ListConnectionsParams,
)

_CONNECTIONS_SECRET = "onepassword_connections"


async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_CONNECTIONS_SECRET)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_CONNECTIONS_SECRET, json.dumps(connections))


async def resolve_connection(ctx, connection_id: str = "") -> dict | None:
    connections = await _load_connections(ctx)
    if not connections:
        return None
    if connection_id:
        return next((c for c in connections if c.get("id") == connection_id), None)
    return connections[0]


async def resolve_or_error(ctx, connection_id: str = ""):
    conn = await resolve_connection(ctx, connection_id)
    if not conn:
        return None, ActionResult.error(
            "No 1Password Connect server found. Connect one with connect_onepassword first.",
            code=oc.OP_NOT_CONNECTED,
        )
    return conn, None


def _connection_to_entity(c: dict) -> OnePasswordConnection:
    return OnePasswordConnection(
        id=c.get("id", ""), label=c.get("label") or "1Password Connect server",
        base_url=c.get("base_url", ""), vault_count=c.get("vault_count", 0),
    )


@chat.function(
    "connect_onepassword",
    "Connect your own 1Password Connect Server (self-hosted, Bearer access token) by saving its base URL "
    "and access token, after checking it actually works.",
    action_type="write", chain_callable=True, data_model=ConnectOnePasswordResult,
    event="1password-connector.connect", effects=["1password.connection.created"],
)
async def connect_onepassword(ctx, params: ConnectOnePasswordParams) -> ActionResult:
    """Verify base_url + access_token against /v1/vaults, then save the connection."""
    base_url = params.base_url.strip()
    access_token = params.access_token.strip()
    if not base_url or not access_token:
        return ActionResult.error(
            "Both the Connect server's base URL and access token are required.",
            code=oc.OP_VALIDATION_FAILED,
        )
    try:
        vaults = await oc.check_connection(ctx, base_url, access_token, params.verify_ssl)
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    vault_count = len(vaults) if isinstance(vaults, list) else 0
    conn = {
        "id": str(uuid.uuid4()),
        "label": params.label.strip(),
        "base_url": base_url,
        "access_token": access_token,
        "verify_ssl": params.verify_ssl,
        "vault_count": vault_count,
    }
    connections = await _load_connections(ctx)
    connections.append(conn)
    await _save_connections(ctx, connections)
    return ActionResult.ok(ConnectOnePasswordResult(
        connection_id=conn["id"], label=conn["label"], vault_count=vault_count,
    ))


@chat.function(
    "list_connections",
    "List the connected 1Password Connect servers.",
    action_type="read", chain_callable=True, data_model=ConnectionList,
)
async def list_connections(ctx, params: ListConnectionsParams) -> ActionResult:
    """List saved 1Password Connect server connections."""
    connections = await _load_connections(ctx)
    return ActionResult.ok(ConnectionList(connections=[_connection_to_entity(c) for c in connections]))


@chat.function(
    "disconnect_onepassword",
    "Disconnect a 1Password Connect server: deletes the saved base URL/access token. Nothing in 1Password "
    "itself is changed.",
    action_type="destructive", chain_callable=True, data_model=DeleteResult,
    event="1password-connector.disconnect", effects=["1password.connection.removed"],
)
async def disconnect_onepassword(ctx, params: DisconnectOnePasswordParams) -> ActionResult:
    """Delete one saved 1Password connection by id."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections):
        return ActionResult.error("No such 1Password connection.", code=oc.OP_NOT_CONNECTED)
    await _save_connections(ctx, remaining)
    return ActionResult.ok(DeleteResult(deleted=True, id=params.connection_id))
