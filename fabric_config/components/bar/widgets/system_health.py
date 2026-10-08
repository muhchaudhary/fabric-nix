"""
System health in the bar: a warning button that shows only while
`config.system_health` has issues, and a popup listing them with what can be
done about each (unit logs and restart, update the pins, clean the store).
"""

import os

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from gi.repository import GLib

import fabric_config.config as config
from fabric_config.services.system_health import PINS_FILES, Issue
from fabric_config.utils.process import run_command_async
from fabric_config.widgets.popup_window_v2 import PopupWindow

ICONS = {
    "unit": "dialog-error-symbolic",
    "pins": "software-update-available-symbolic",
    "disk": "drive-harddisk-symbolic",
    "reboot": "system-reboot-symbolic",
}
# a restarted unit takes a moment to settle (or fail again)
RECHECK_MS = 2000


def _in_terminal(command: str):
    """Run a shell command in a terminal, left open to read the result."""
    script = f"{command}; echo; read -r -p 'Press Enter to close' _"
    run_command_async(["uwsm", "app", "-t", "service", "-T", "--", "sh", "-c", script])


def _notify(summary: str, body: str):
    run_command_async(
        [
            "notify-send",
            "-a",
            "System Health",
            "-i",
            "dialog-warning-symbolic",
            summary,
            body,
        ]
    )


class SystemHealthPanel(Box):
    def __init__(self, **kwargs):
        super().__init__(name="health-panel", orientation="v", spacing=10, **kwargs)
        self.summary = Label("", name="health-summary", h_align="start")
        self.rows = Box(orientation="v", spacing=8)
        self.children = [
            Box(
                orientation="v",
                children=[
                    Label("System health", name="health-title", h_align="start"),
                    self.summary,
                ],
            ),
            self.rows,
        ]
        config.system_health.connect("changed", lambda *_: self.update())
        self.update()

    def update(self):
        for child in self.rows.get_children():
            child.destroy()
        issues = config.system_health.issues
        count = len(issues)
        self.summary.set_label(
            "All good"
            if not count
            else f"{count} thing{'s' if count != 1 else ''} to look at"
        )
        for issue in issues:
            self.rows.add(self._row(issue))
        self.rows.show_all()

    def _row(self, issue: Issue) -> Box:
        actions = [self._button(label, callback) for label, callback in _actions(issue)]
        actions.append(
            self._button("Dismiss", lambda: config.system_health.dismiss(issue))
        )
        return Box(
            name="health-issue",
            spacing=10,
            children=[
                Image(
                    icon_name=ICONS.get(issue.kind, "dialog-warning-symbolic"),
                    icon_size=20,
                    v_align="start",
                ),
                Box(
                    orientation="v",
                    spacing=6,
                    h_expand=True,
                    children=[
                        Label(
                            issue.title,
                            name="health-issue-title",
                            h_align="start",
                            ellipsization="end",
                        ),
                        Label(
                            issue.detail,
                            name="health-issue-detail",
                            h_align="start",
                            ellipsization="end",
                        ),
                        Box(spacing=6, children=actions),
                    ],
                ),
            ],
        )

    @staticmethod
    def _button(label: str, callback) -> Button:
        return Button(
            label=label,
            name="health-action",
            on_clicked=lambda *_: callback(),
        )


def _actions(issue: Issue) -> list[tuple[str, object]]:
    if issue.kind == "unit" and issue.unit:
        scope = "--user " if issue.user else ""

        def restart():
            argv = [
                "systemctl",
                *(["--user"] if issue.user else []),
                "restart",
                issue.unit,
            ]

            def on_done(success: bool, _out: str, err: str):
                if not success:
                    _notify(f"Couldn't restart {issue.unit}", err.strip())
                GLib.timeout_add(
                    RECHECK_MS, lambda: config.system_health.refresh() or False
                )

            run_command_async(argv, on_done)

        return [
            (
                "Logs",
                lambda: _close_then(
                    lambda: _in_terminal(f"journalctl {scope}-u {issue.unit} -e")
                ),
            ),
            ("Restart", restart),
        ]
    if issue.kind == "pins":
        path = next((p for p in PINS_FILES if p and os.path.exists(p)), "")
        if path.endswith("sources.json"):
            command = (
                f"cd {_quote(os.path.dirname(os.path.dirname(path)))} && npins update"
            )
        else:
            command = f"cd {_quote(os.path.dirname(path))} && nix flake update"
        return [("Update", lambda: _close_then(lambda: _in_terminal(command)))]
    if issue.kind == "disk":
        return [
            ("Clean up", lambda: _close_then(lambda: _in_terminal("nix-store --gc")))
        ]
    return []


def _quote(path: str) -> str:
    return "'" + path.replace("'", "'\\''") + "'"


def _close_then(action):
    if SystemHealthPopup.popup_visible:
        SystemHealthPopup.toggle_popup()
    action()


SystemHealthPopup = PopupWindow(
    transition_duration=350,
    anchor="top-right",
    transition_type="slide-down",
    child=SystemHealthPanel(),
    enable_inhibitor=True,
)


class SystemHealthButton(Button):
    """Shown only while something needs a look."""

    def __init__(self, **kwargs):
        super().__init__(
            name="health-button",
            style_classes=["button-basic", "button-basic-props", "button-border"],
            tooltip_text="System health",
            on_clicked=lambda *_: self._toggle_popup(),
            **kwargs,
        )
        self.count = Label("", name="health-count")
        self.add(
            Box(
                spacing=4,
                children=[
                    Image(icon_name="dialog-warning-symbolic", icon_size=18),
                    self.count,
                ],
            )
        )
        # hidden while all is well, whatever show_all() the bar runs
        self.set_no_show_all(True)
        config.system_health.connect("changed", lambda *_: self.update())
        self.update()

    def update(self):
        issues = config.system_health.issues
        self.count.set_label(str(len(issues)))
        self.set_tooltip_text("\n".join(i.title for i in issues) or "System health")
        self.set_visible(bool(issues))
        if not issues and SystemHealthPopup.popup_visible:
            SystemHealthPopup.toggle_popup()

    def _toggle_popup(self):
        if not SystemHealthPopup.popup_visible:
            config.system_health.refresh()
            SystemHealthPopup.place_under(self)
        SystemHealthPopup.toggle_popup()
