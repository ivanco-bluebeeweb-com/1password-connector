"""Value-add reports for 1Password Connector -- vault health overview and
stale-item detection, same "aggregate raw records into one glance" shape
as every other connector's handlers_reports.py this session.
"""
from __future__ import annotations

import datetime as _dt

from imperal_sdk import ActionResult

import onepassword_client as oc
from app import chat
from handlers_connection import resolve_or_error
from schemas import (
    AuditVaultHealthParams, VaultHealthReport, VaultHealthSummary,
    GetStaleItemsReportParams, StaleItemsReport, StaleItem,
)


@chat.function(
    "audit_vault_health",
    "Build one aggregated health report across every vault this Connect server can reach: item count and "
    "category breakdown per vault.",
    action_type="read", chain_callable=True, data_model=VaultHealthReport,
)
async def audit_vault_health(ctx, params: AuditVaultHealthParams) -> ActionResult:
    """Scan every reachable vault and summarize item counts by category."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        vaults = await oc.request(ctx, conn, "GET", "/vaults", action="list vaults for audit")
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    summaries: list[VaultHealthSummary] = []
    total_items = 0
    for v in (vaults or []):
        vault_id = v.get("id", "")
        try:
            items = await oc.request(ctx, conn, "GET", f"/vaults/{vault_id}/items", action="list items for audit")
        except oc.ClientFail:
            items = []
        by_category: dict[str, int] = {}
        for i in (items or []):
            cat = i.get("category", "UNKNOWN")
            by_category[cat] = by_category.get(cat, 0) + 1
        count = len(items or [])
        total_items += count
        summaries.append(VaultHealthSummary(
            vault_id=vault_id, vault_name=v.get("name", ""), item_count=count, by_category=by_category,
        ))
    return ActionResult.ok(VaultHealthReport(
        vault_count=len(summaries), total_items=total_items, vaults=summaries,
    ))


@chat.function(
    "get_stale_items_report",
    "Value-add report: scan one vault's items and flag every one not updated in at least the given number "
    "of days -- candidates for password rotation review.",
    action_type="read", chain_callable=True, data_model=StaleItemsReport,
)
async def get_stale_items_report(ctx, params: GetStaleItemsReportParams) -> ActionResult:
    """Scan a vault's items and flag stale ones by updatedAt age."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        items = await oc.request(
            ctx, conn, "GET", f"/vaults/{params.vault_id}/items", action="list items for stale report",
        )
    except oc.ClientFail as exc:
        return ActionResult.error(exc.payload["message"], code=exc.payload["code"])
    now = _dt.datetime.now(_dt.timezone.utc)
    stale: list[StaleItem] = []
    for i in (items or []):
        updated_raw = i.get("updatedAt", "")
        if not updated_raw:
            continue
        try:
            updated_at = _dt.datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        days = (now - updated_at).days
        if days >= params.min_days_stale:
            stale.append(StaleItem(
                item_id=i.get("id", ""), title=i.get("title", ""), category=i.get("category", ""),
                days_since_update=days, updated_at=updated_raw,
            ))
    stale.sort(key=lambda x: x.days_since_update, reverse=True)
    return ActionResult.ok(StaleItemsReport(count=len(stale), items=stale))
