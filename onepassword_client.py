"""Thin HTTP client for the 1Password Connect Server REST API.

Same "fail()-dict + ClientFail exception + generic request() helper"
shape as every other connector this session's *_client.py. Confirmed
against 1password.dev/connect/api-reference, 2026-08-29:

- Bearer access token auth (issued when the Connect server is set up).
- Vaults are scoped to whatever the token/server was granted at deploy
  time -- there's no "list all vaults in the account".
- Items support full CRUD plus RFC6902 JSON Patch for partial updates.
- Files are read-only (list/get metadata/get content), no create/delete.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

OP_NOT_CONNECTED = "ONEPASSWORD_NOT_CONNECTED"
OP_UNAUTHORIZED = "ONEPASSWORD_UNAUTHORIZED"
OP_FORBIDDEN = "ONEPASSWORD_FORBIDDEN"
OP_NOT_FOUND = "ONEPASSWORD_NOT_FOUND"
OP_RATE_LIMITED = "ONEPASSWORD_RATE_LIMITED"
OP_BACKEND_ERROR = "ONEPASSWORD_BACKEND_ERROR"
OP_VALIDATION_FAILED = "ONEPASSWORD_VALIDATION_FAILED"
OP_RESPONSE_UNEXPECTED = "ONEPASSWORD_RESPONSE_UNEXPECTED"

_MESSAGES = {
    OP_NOT_CONNECTED: "No 1Password Connect server found. Connect one first.",
    OP_UNAUTHORIZED: "1Password rejected the access token as invalid or expired.",
    OP_FORBIDDEN: "1Password denied access -- this token's Connect server was not granted this vault/item.",
    OP_NOT_FOUND: "That 1Password record was not found.",
    OP_RATE_LIMITED: "1Password Connect server rate-limited this request. Try again shortly.",
    OP_BACKEND_ERROR: "1Password Connect server returned an error.",
    OP_VALIDATION_FAILED: "1Password rejected the request as invalid.",
    OP_RESPONSE_UNEXPECTED: "1Password Connect server returned an unexpected response shape.",
}


class ClientFail(Exception):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("message", "1Password request failed"))


def fail(code: str, detail: str = "") -> dict:
    msg = _MESSAGES.get(code, "1Password request failed.")
    if detail:
        msg = f"{msg} ({detail})"
    return {"ok": False, "code": code, "message": msg}


def parse_fields_json(fields_json: str) -> dict | None:
    try:
        data = json.loads(fields_json)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _headers(access_token: str, content_type: str = "application/json") -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": content_type,
    }


def _check_status(resp: httpx.Response, action: str) -> Any:
    if resp.status_code == 401:
        raise ClientFail(fail(OP_UNAUTHORIZED, action))
    if resp.status_code == 403:
        raise ClientFail(fail(OP_FORBIDDEN, action))
    if resp.status_code == 404:
        raise ClientFail(fail(OP_NOT_FOUND, action))
    if resp.status_code == 429:
        raise ClientFail(fail(OP_RATE_LIMITED, action))
    if resp.status_code == 422:
        raise ClientFail(fail(OP_VALIDATION_FAILED, f"{action}: {resp.text[:300]}"))
    if resp.status_code >= 500:
        raise ClientFail(fail(OP_BACKEND_ERROR, f"{action}: HTTP {resp.status_code}"))
    if resp.status_code >= 400:
        raise ClientFail(fail(OP_BACKEND_ERROR, f"{action}: HTTP {resp.status_code} {resp.text[:300]}"))
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        raise ClientFail(fail(OP_RESPONSE_UNEXPECTED, f"{action}: non-JSON response"))


async def request(ctx, conn: dict, method: str, path: str, *, params: dict | None = None,
                   json_body: Any = None, action: str = "request") -> Any:
    """Generic authenticated call against a connection's own Connect server base_url."""
    base_url = (conn.get("base_url") or "").rstrip("/")
    access_token = conn.get("access_token", "")
    if not base_url or not access_token:
        raise ClientFail(fail(OP_NOT_CONNECTED))
    url = f"{base_url}/v1{path}"
    headers = _headers(access_token)
    async with httpx.AsyncClient(timeout=30, verify=conn.get("verify_ssl", True)) as client:
        resp = await client.request(method, url, headers=headers, params=params, json=json_body)
    return _check_status(resp, action)


async def request_raw(ctx, conn: dict, method: str, path: str, *, action: str = "request") -> bytes:
    """Like request(), but returns raw bytes -- used for get_file_content (binary content)."""
    base_url = (conn.get("base_url") or "").rstrip("/")
    access_token = conn.get("access_token", "")
    if not base_url or not access_token:
        raise ClientFail(fail(OP_NOT_CONNECTED))
    url = f"{base_url}/v1{path}"
    headers = _headers(access_token)
    async with httpx.AsyncClient(timeout=30, verify=conn.get("verify_ssl", True)) as client:
        resp = await client.request(method, url, headers=headers)
    if resp.status_code >= 400:
        _check_status(resp, action)
    return resp.content


async def check_connection(ctx, base_url: str, access_token: str, verify_ssl: bool = True) -> dict:
    """Ping /v1/vaults to prove base_url + access_token actually work before saving a connection."""
    url = f"{base_url.rstrip('/')}/v1/vaults"
    headers = _headers(access_token)
    async with httpx.AsyncClient(timeout=15, verify=verify_ssl) as client:
        resp = await client.get(url, headers=headers)
    return _check_status(resp, "verify connection")
