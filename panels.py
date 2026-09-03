"""Panel UI -- connections list/connect form + the one required "App
settings" entry point, same shape as CyberArk/Ansible Connector's panels.py.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule. Disconnect lives only in the
"App settings" screen (panels_settings.py). The one secondary "App
settings" button is always the LAST element at the bottom of the sidebar.

PER ~/UI_INTERFACE_STANDARD.md (2026-08-21 addendum): every Input carries
its own visible label, the placeholder text is always contextually
specific, the form's own container is stretched to the full width of the
left sidebar, and the form's inner content is stretched to fill that
container. The "How do I set this up?" instructions live ONLY in the help
modal below -- never duplicated as static sidebar text.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers_connection as h


def _settings_button() -> ui.UINode:
    return ui.Button(
        "App settings", variant="secondary", size="sm", icon="settings", on_click=ui.Call("__panel__onepassword_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or "1Password Connect server"
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(label, variant="body"),
        ui.Text(f"{c.get('base_url', '')} -- {c.get('vault_count', 0)} vault(s)", variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No 1Password Connect servers connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _help_modal() -> ui.UINode:
    return ui.Modal(
        trigger=ui.Button("How do I set this up?", variant="link", size="sm"),
        title="Connecting 1Password",
        children=[
            ui.Stack(direction="v", gap=2, children=[
                ui.Text("1. In 1Password Business, go to Integrations > Connect Servers and create a new server.", variant="body"),
                ui.Text("2. Deploy the Connect server (Docker/Kubernetes) using the downloaded credentials file.", variant="body"),
                ui.Text("3. Grant the server access to the vaults you want this connector to reach.", variant="body"),
                ui.Text("4. Generate an access token for it, and paste the server's URL + token below.", variant="body"),
            ]),
        ],
    )


@ext.panel("sidebar", slot="left")
async def sidebar(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)
    return ui.Stack(direction="v", gap=3, children=[
        ui.Text("1Password", variant="heading"),
        _connections_section(connections),
        ui.Divider(),
        ui.Form(
            submit_label="Connect",
            action=ui.Call("connect_onepassword"),
            children=[
                ui.Stack(direction="v", gap=1, children=[
                    ui.Text("Label", variant="label"),
                    ui.Input(param_name="label", placeholder="e.g. Prod vaults"),
                ]),
                ui.Stack(direction="v", gap=1, children=[
                    ui.Text("Connect server URL", variant="label"),
                    ui.Input(param_name="base_url", placeholder="https://connect.yourcompany.com"),
                ]),
                ui.Stack(direction="v", gap=1, children=[
                    ui.Text("Access token", variant="label"),
                    ui.Input(param_name="access_token", placeholder="Access token from the Connect server setup"),
                ]),
            ],
        ),
        _help_modal(),
        ui.Divider(),
        _settings_button(),
    ])
