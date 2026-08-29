"""Pydantic param/result models for 1Password Connector.

Same "explicit AccountScoped/ConnectionScoped mixin + one params + one
result class per @chat.function" shape as every other connector this
session's schemas.py.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectionScoped(BaseModel):
    connection_id: str = Field("", description="Which saved 1Password Connect server to use. Omit if only one is connected.")


# ── Connection lifecycle ────────────────────────────────────────────────

class ConnectOnePasswordParams(BaseModel):
    label: str = Field("", description="A friendly name for this Connect server, e.g. 'Prod vaults'.")
    base_url: str = Field(description="Your 1Password Connect server's base URL, e.g. https://connect.yourcompany.com")
    access_token: str = Field(description="The access token issued when you set up this Connect server (1Password Business admin console).")
    verify_ssl: bool = Field(True, description="Verify the Connect server's TLS certificate. Turn off only for self-signed certs in trusted internal networks.")


class ConnectOnePasswordResult(BaseModel):
    connection_id: str = ""
    label: str = ""
    vault_count: int = 0


class DisconnectOnePasswordParams(BaseModel):
    connection_id: str = Field(description="The connection id to disconnect, from list_connections.")


class DeleteResult(BaseModel):
    deleted: bool = False
    id: str = ""


class ListConnectionsParams(BaseModel):
    pass


class OnePasswordConnection(BaseModel):
    id: str = ""
    label: str = ""
    base_url: str = ""
    vault_count: int = 0


class ConnectionList(BaseModel):
    connections: list[OnePasswordConnection] = Field(default_factory=list)


# ── Vaults ───────────────────────────────────────────────────────────────

class ListVaultsParams(ConnectionScoped):
    pass


class Vault(BaseModel):
    id: str = ""
    name: str = ""
    attribute_version: int = 0
    content_version: int = 0
    items: int = 0
    type: str = ""
    created_at: str = ""
    updated_at: str = ""


class VaultList(BaseModel):
    vaults: list[Vault] = Field(default_factory=list)


class GetVaultParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")


# ── Items ────────────────────────────────────────────────────────────────

class ListItemsParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    filter_query: str = Field("", description="1Password filter expression, e.g. \"title eq \\\"Prod DB\\\"\". Leave empty to list everything.")


class ItemSummary(BaseModel):
    id: str = ""
    title: str = ""
    category: str = ""
    vault_id: str = ""
    favorite: bool = False
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class ItemList(BaseModel):
    items: list[ItemSummary] = Field(default_factory=list)


class GetItemParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    item_id: str = Field(description="The item's id, from list_items.")


class ItemDetail(BaseModel):
    id: str = ""
    title: str = ""
    category: str = ""
    vault_id: str = ""
    favorite: bool = False
    tags: list[str] = Field(default_factory=list)
    fields: list[dict] = Field(default_factory=list, description="Every field on the item, INCLUDING secret values (passwords, API keys) -- this is the whole point of reading an item.")
    urls: list[dict] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class CreateItemParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id to create the item in, from list_vaults.")
    title: str = Field(description="The item's display title.")
    category: str = Field("LOGIN", description="Item category: LOGIN, PASSWORD, SECURE_NOTE, API_CREDENTIAL, SERVER, DATABASE, CREDIT_CARD, IDENTITY, or others 1Password supports.")
    fields_json: str = Field(description="JSON array of field objects, e.g. '[{\"label\":\"username\",\"value\":\"admin\",\"purpose\":\"USERNAME\"},{\"label\":\"password\",\"value\":\"secret\",\"purpose\":\"PASSWORD\"}]'.")
    tags: list[str] = Field(default_factory=list, description="Tags to apply to the new item.")


class UpdateItemParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    item_id: str = Field(description="The item's id to replace, from list_items.")
    title: str = Field(description="The item's display title (required even if unchanged -- this is a full replace).")
    category: str = Field(description="The item's category (required even if unchanged).")
    fields_json: str = Field(description="JSON array of the item's full new field list, same shape as create_item's fields_json.")
    tags: list[str] = Field(default_factory=list, description="The item's full new tag list.")


class PatchItemParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    item_id: str = Field(description="The item's id to patch, from list_items.")
    patch_json: str = Field(description="JSON array of RFC6902 JSON Patch operations, e.g. '[{\"op\":\"replace\",\"path\":\"/title\",\"value\":\"New name\"}]'.")


class DeleteItemParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    item_id: str = Field(description="The item's id to delete, from list_items.")


class WriteResult(BaseModel):
    ok: bool = False
    id: str = ""
    record: dict = Field(default_factory=dict)


# ── Files ────────────────────────────────────────────────────────────────

class ListFilesParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    item_id: str = Field(description="The item's id whose file attachments to list, from list_items.")


class FileSummary(BaseModel):
    id: str = ""
    name: str = ""
    size: int = 0
    content_path: str = ""


class FileList(BaseModel):
    files: list[FileSummary] = Field(default_factory=list)


class GetFileParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    item_id: str = Field(description="The item's id, from list_items.")
    file_id: str = Field(description="The file's id, from list_files.")


class FileDetail(BaseModel):
    id: str = ""
    name: str = ""
    size: int = 0
    content_path: str = ""


class GetFileContentParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id, from list_vaults.")
    item_id: str = Field(description="The item's id, from list_items.")
    file_id: str = Field(description="The file's id, from list_files.")


class FileContent(BaseModel):
    id: str = ""
    name: str = ""
    content_base64: str = ""


# ── API activity (audit trail) ──────────────────────────────────────────

class ListApiActivityParams(ConnectionScoped):
    limit: int = Field(100, ge=1, le=500, description="Number of recent API activity entries to return.")


class ApiActivityEntry(BaseModel):
    timestamp: str = ""
    action: str = ""
    result: str = ""
    request_id: str = ""


class ApiActivityList(BaseModel):
    entries: list[ApiActivityEntry] = Field(default_factory=list)


# ── Value-add reports ───────────────────────────────────────────────────

class AuditVaultHealthParams(ConnectionScoped):
    pass


class VaultHealthSummary(BaseModel):
    vault_id: str = ""
    vault_name: str = ""
    item_count: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)


class VaultHealthReport(BaseModel):
    vault_count: int = 0
    total_items: int = 0
    vaults: list[VaultHealthSummary] = Field(default_factory=list)


class GetStaleItemsReportParams(ConnectionScoped):
    vault_id: str = Field(description="The vault's id to scan, from list_vaults.")
    min_days_stale: int = Field(180, ge=1, description="Minimum number of days since last update to flag an item as stale.")


class StaleItem(BaseModel):
    item_id: str = ""
    title: str = ""
    category: str = ""
    days_since_update: int = 0
    updated_at: str = ""


class StaleItemsReport(BaseModel):
    count: int = 0
    items: list[StaleItem] = Field(default_factory=list)
