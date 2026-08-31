"""Vaults, Items, Files, and API activity for 1Password Connector.

Confirmed against 1password.dev/connect/api-reference, 2026-08-29:
GET /v1/vaults, GET /v1/vaults/{id}, GET /v1/vaults/{id}/items,
POST /v1/vaults/{id}/items, GET/PUT/DELETE /v1/vaults/{id}/items/{id},
PATCH /v1/vaults/{id}/items/{id} (RFC6902 JSON Patch),
GET /v1/vaults/{id}/items/{id}/files,
GET /v1/vaults/{id}/items/{id}/files/{id},
GET /v1/vaults/{id}/items/{id}/files/{id}/content,
GET /v1/activity.
"""
from __future__ import annotations

import base64

from imperal_sdk import ActionResult

import onepassword_client as oc
from app import chat
from handlers_connection import resolve_or_error
from schemas import (
    ListVaultsParams, VaultList, Vault,
    GetVaultParams,
    ListItemsParams, ItemList, ItemSummary,
    GetItemParams, ItemDetail,
    CreateItemParams,
    UpdateItemParams,
    DeleteItemParams, DeleteResult,
    ListFilesParams, FileList, FileSummary,
    GetFileParams, FileDetail,
    GetFileContentParams, FileContent,
    ListApiActivityParams, ApiActivityList, ApiActivityEntry,
)


def _vault_to_entity(v: dict) -> Vault:
    return Vault(
        id=v.get("id", ""), name=v.get("name", ""),
        attribute_version=v.get("attributeVersion", 0), content_version=v.get("contentVersion", 0),
        items=v.get("items", 0), type=v.get("type", ""),
        created_at=v.get("createdAt", ""), updated_at=v.get("updatedAt", ""),
    )


def _item_summary(i: dict) -> ItemSummary:
    return ItemSummary(
        id=i.get("id", ""), title=i.get("title", ""), category=i.get("category", ""),
        vault_id=(i.get("vault", {}) or {}).get("id", ""), favorite=i.get("favorite", False),
        tags=i.get("tags", []) or [], created_at=i.get("createdAt", ""), updated_at=i.get("updatedAt", ""),
    )


def _item_detail(i: dict) -> ItemDetail:
    return ItemDetail(
        id=i.get("id", ""), title=i.get("title", ""), category=i.get("category", ""),
        vault_id=(i.get("vault", {}) or {}).get("id", ""), favorite=i.get("favorite", False),
        tags=i.get("tags", []) or [], fields=i.get("fields", []) or [], urls=i.get("urls", []) or [],
        created_at=i.get("createdAt", ""), updated_at=i.get("updatedAt", ""),
    )


@chat.function(
    "list_vaults",
    "List vaults this 1Password Connect server was granted access to. There is no way to list every vault "
    "in the account -- only the ones this server's token can reach.",
    action_type="read", chain_callable=True, data_model=VaultList,
)
async def list_vaults(ctx, params: ListVaultsParams) -> ActionResult:
    """List vaults reachable by the connected Connect server."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        vaults = await oc.request(ctx, conn, "GET", "/vaults", action="list vaults")
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(VaultList(vaults=[_vault_to_entity(v) for v in (vaults or [])]), summary="Vaults listed.")


@chat.function(
    "get_vault",
    "Read one vault's metadata in full by id.",
    action_type="read", chain_callable=True, data_model=Vault,
)
async def get_vault(ctx, params: GetVaultParams) -> ActionResult:
    """Read one vault by id."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        v = await oc.request(ctx, conn, "GET", f"/vaults/{params.vault_id}", action="get vault")
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(_vault_to_entity(v), summary="Vault retrieved.")


@chat.function(
    "list_items",
    "List items (logins, passwords, secure notes, API credentials, and more) inside one vault. "
    "Item summaries do NOT include secret field values -- use get_item for those.",
    action_type="read", chain_callable=True, data_model=ItemList,
)
async def list_items(ctx, params: ListItemsParams) -> ActionResult:
    """List items in a vault, optionally filtered."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query_params = {}
    if params.filter_query.strip():
        query_params["filter"] = params.filter_query.strip()
    try:
        items = await oc.request(
            ctx, conn, "GET", f"/vaults/{params.vault_id}/items",
            params=query_params or None, action="list items",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(ItemList(items=[_item_summary(i) for i in (items or [])]), summary="Items listed.")


@chat.function(
    "get_item",
    "Read one item in full, INCLUDING its secret field values (passwords, API keys, private notes). "
    "This exposes real credentials -- use only when you actually need the secret value.",
    action_type="read", chain_callable=True, data_model=ItemDetail,
)
async def get_item(ctx, params: GetItemParams) -> ActionResult:
    """Read one item in full, secrets included."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        i = await oc.request(
            ctx, conn, "GET", f"/vaults/{params.vault_id}/items/{params.item_id}", action="get item",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(_item_detail(i), summary="Item retrieved.")


@chat.function(
    "create_item",
    "Create a new item (login, password, secure note, API credential, etc) in a vault. Cannot create "
    "CUSTOM or DOCUMENT category items -- 1Password's own API restriction.",
    action_type="write", chain_callable=True, data_model=ItemDetail,
    event="1password-connector.item_created", effects=["1password.item.created"],
)
async def create_item(ctx, params: CreateItemParams) -> ActionResult:
    """Create a new item from an item_json payload (1Password's own item shape)."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    body = oc.parse_fields_json(params.item_json)
    if body is None:
        return ActionResult.error("item_json must be a valid JSON object.", code=oc.OP_VALIDATION_FAILED)
    body.setdefault("vault", {"id": params.vault_id})
    try:
        i = await oc.request(
            ctx, conn, "POST", f"/vaults/{params.vault_id}/items", json_body=body, action="create item",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(_item_detail(i), summary="Item created.")


@chat.function(
    "update_item",
    "Update selected fields of an existing item using RFC6902 JSON Patch operations (add/remove/replace). "
    "Only the given operations change; everything else on the item stays as-is.",
    action_type="write", chain_callable=True, data_model=ItemDetail,
    event="1password-connector.item_updated", effects=["1password.item.updated"],
)
async def update_item(ctx, params: UpdateItemParams) -> ActionResult:
    """Apply a JSON Patch document to an existing item."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    patch = oc.parse_fields_json(params.patch_json)
    if patch is None or not isinstance(patch, (list, dict)):
        return ActionResult.error(
            "patch_json must be a valid JSON array of RFC6902 patch operations, e.g. "
            '[{"op": "replace", "path": "/title", "value": "New title"}]',
            code=oc.OP_VALIDATION_FAILED,
        )
    try:
        import json as _json
        patch_list = _json.loads(params.patch_json)
        i = await oc.request(
            ctx, conn, "PATCH", f"/vaults/{params.vault_id}/items/{params.item_id}",
            json_body=patch_list, action="update item",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(_item_detail(i), summary="Item updated.")


@chat.function(
    "delete_item",
    "Permanently delete an item from a vault. Cannot be undone.",
    action_type="destructive", chain_callable=True, data_model=DeleteResult,
    event="1password-connector.item_deleted", effects=["1password.item.deleted"],
)
async def delete_item(ctx, params: DeleteItemParams) -> ActionResult:
    """Delete an item by id."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        await oc.request(
            ctx, conn, "DELETE", f"/vaults/{params.vault_id}/items/{params.item_id}", action="delete item",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(DeleteResult(deleted=True, id=params.item_id), summary="Item deleted.")


@chat.function(
    "list_files",
    "List file attachments on an item (e.g. a document or image attached to a secure note).",
    action_type="read", chain_callable=True, data_model=FileList,
)
async def list_files(ctx, params: ListFilesParams) -> ActionResult:
    """List an item's file attachments."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        files = await oc.request(
            ctx, conn, "GET", f"/vaults/{params.vault_id}/items/{params.item_id}/files",
            action="list files",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(FileList(files=[
        FileSummary(id=f.get("id", ""), name=f.get("name", ""), size=f.get("size", 0))
        for f in (files or [])
    ]), summary="Files listed.")


@chat.function(
    "get_file",
    "Read one file attachment's metadata (name, size) by id.",
    action_type="read", chain_callable=True, data_model=FileDetail,
)
async def get_file(ctx, params: GetFileParams) -> ActionResult:
    """Read one file's metadata."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        f = await oc.request(
            ctx, conn, "GET",
            f"/vaults/{params.vault_id}/items/{params.item_id}/files/{params.file_id}",
            action="get file",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(FileDetail(
        id=f.get("id", ""), name=f.get("name", ""), size=f.get("size", 0),
        content_path=f.get("content_path", ""),
    ), summary="File retrieved.")


@chat.function(
    "get_file_content",
    "Download a file attachment's actual content, base64-encoded. Exposes real file data -- use only "
    "when you actually need the file's bytes.",
    action_type="read", chain_callable=True, data_model=FileContent,
)
async def get_file_content(ctx, params: GetFileContentParams) -> ActionResult:
    """Download a file's raw content."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        raw = await oc.request_raw(
            ctx, conn, "GET",
            f"/vaults/{params.vault_id}/items/{params.item_id}/files/{params.file_id}/content",
            action="get file content",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    return ActionResult.success(FileContent(
        id=params.file_id, name="", content_base64=base64.b64encode(raw).decode("ascii"),
    ), summary="File content retrieved.")


@chat.function(
    "list_api_activity",
    "List API activity (audit trail) for this Connect server's own access token usage.",
    action_type="read", chain_callable=True, data_model=ApiActivityList,
)
async def list_api_activity(ctx, params: ListApiActivityParams) -> ActionResult:
    """List recent API activity entries."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        data = await oc.request(
            ctx, conn, "GET", "/activity", params={"limit": params.limit}, action="list API activity",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    rows = data if isinstance(data, list) else (data.get("items", []) if isinstance(data, dict) else [])
    return ActionResult.success(ApiActivityList(entries=[
        ApiActivityEntry(
            timestamp=r.get("timestamp", ""), action=r.get("action", ""),
            result=r.get("result", ""), request_id=r.get("request_id", ""),
        )
        for r in rows
    ]), summary="Api activity listed.")
