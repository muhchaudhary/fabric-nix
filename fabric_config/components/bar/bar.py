from typing import Callable, Iterable, Literal, override

from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.shapes import Corner
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gtk

from fabric_config.components.bar.widgets import (
    BatteryIndicator,
    PrayerTimesButton,
    SystemTemps,
    SystemTrayRevealer,
)
from fabric_config.components.bar.widgets.clipboard_history import (
    ClipboardHistoryButton,
)
from fabric_config.components.bar.widgets.notification_center import (
    NotificationCenterButton,
)
from fabric_config.components.bar.widgets.power_menu import PowerMenuButton
from fabric_config.components.bar.widgets.system_health import SystemHealthButton
from fabric_config.components.bar.widgets.recording_indicator import (
    RecordingIndicator,
)
from fabric_config.components.bar.widgets.wallpaper_picker import WallpapperPickerButton
from fabric_config.components.quick_settings.quick_settings import QuickSettingsButton
from fabric_config.utils.hyprland_windows import hyprland_clients
from fabric_config.utils.icon_resolver import get_icon_resolver


class HyprlandWorkspaceFix(HyprlandWorkspaces):
    def __init__(
        self,
        buttons: Iterable[WorkspaceButton] | None = None,
        buttons_factory: Callable[[int], WorkspaceButton | None]
        | None = HyprlandWorkspaces.default_buttons_factory,
        invert_scroll: bool = False,
        empty_scroll: bool = False,
        **kwargs,
    ):
        super().__init__(
            buttons, buttons_factory, invert_scroll, empty_scroll, **kwargs
        )

    # override signals again to use lua syntax
    @override
    def do_action_next(self):
        target = "e+1" if not self._empty_scroll else "+1"
        return self.connection.send_command(
            f"/dispatch hl.dsp.focus({{ workspace = '{target}' }})"
        )

    @override
    def do_action_previous(self):
        target = "e-1" if not self._empty_scroll else "-1"

        return self.connection.send_command(
            f"/dispatch hl.dsp.focus({{ workspace = '{target}' }})"
        )

    @override
    def do_button_clicked(self, button: WorkspaceButton):
        return self.connection.send_command(
            f"/dispatch hl.dsp.focus({{ workspace = {button.id} }})"
        )


class StatusBarCorner(Box):
    def __init__(self, corner: Literal["top-right", "top-left"]):
        super().__init__(
            # style="margin-bottom: 25px;",
            orientation="vertical",
            h_expand=False,
            v_expand=False,
            name="system-bar-corner",
            children=[
                Corner(
                    orientation=corner,
                    size=10,
                ),
                Box(
                    v_expand=True,
                    style="background-color: unset;",
                ),
            ],
        )


class BarDivider(Box):
    """A short hairline between clusters of bar buttons."""

    def __init__(self):
        super().__init__(name="bar-divider", v_align="center")


def workspace_tooltip(button: WorkspaceButton, tooltip: Gtk.Tooltip) -> bool:
    """On hover: the icons and titles of the windows on that workspace."""
    clients = [
        c
        for c in hyprland_clients()
        if (c.get("workspace") or {}).get("id") == button.id
    ]
    icons = get_icon_resolver()
    rows: list[Gtk.Widget] = [
        Label(f"Workspace {button.id}", name="workspace-tooltip-title", h_align="start")
    ]
    if not clients:
        rows.append(Label("Empty", name="workspace-tooltip-empty", h_align="start"))
    for client in clients[:8]:
        app_class = client.get("class") or ""
        rows.append(
            Box(
                spacing=8,
                children=[
                    Image(pixbuf=icons.get_icon_pixbuf(app_class, 20)),
                    Label(
                        client.get("title") or app_class,
                        max_chars_width=40,
                        ellipsization="end",
                        h_align="start",
                    ),
                ],
            )
        )
    if len(clients) > 8:
        rows.append(Label(f"+{len(clients) - 8} more", name="workspace-tooltip-empty"))
    content = Box(orientation="v", spacing=6, children=rows)
    content.show_all()
    tooltip.set_custom(content)
    return True


class StatusBarSeperated(WaylandWindow):
    def __init__(self):
        self.bar_content = CenterBox(name="system-bar")

        self.workspace_buttons = [
            WorkspaceButton(
                i,
                style_classes=[
                    "button-basic",
                    "button-basic-props",
                    "button-border",
                ],
            )
            for i in range(1, 7)
        ]
        for button in self.workspace_buttons:
            button.set_has_tooltip(True)
            button.connect(
                "query-tooltip", lambda b, _x, _y, _kb, tip: workspace_tooltip(b, tip)
            )
        self.workspaces = HyprlandWorkspaceFix(
            name="workspaces",
            spacing=2,
            buttons=self.workspace_buttons,
            buttons_factory=None,
        )

        self.recording_indicator = RecordingIndicator()

        # self.open_apps_bar = OpenAppsBar()
        self.date_time = DateTime(
            formatters="%a %b %d  %I:%M %p",
            style_classes=["button-basic", "button-basic-props", "button-border"],
        )
        self.battery = BatteryIndicator()
        self.quick_settings = QuickSettingsButton()
        self.notification_button = NotificationCenterButton()
        self.prayer_times = PrayerTimesButton()
        self.wallpaper_button = WallpapperPickerButton()
        self.clipboard_button = ClipboardHistoryButton()
        self.system_temps = SystemTemps()
        self.system_health = SystemHealthButton()
        self.system_tray = SystemTrayRevealer(icon_size=25)

        self.power_menu = PowerMenuButton()

        self.bar_content.end_children = [
            StatusBarCorner("top-right"),
            Box(
                name="system-bar-group",
                # clusters: readouts | status and settings | clock | power
                children=[
                    self.recording_indicator,
                    self.system_health,
                    self.system_temps,
                    BarDivider(),
                    self.system_tray,
                    self.notification_button,
                    self.quick_settings,
                    self.battery,
                    BarDivider(),
                    self.date_time,
                    BarDivider(),
                    self.power_menu,
                ],
                style_classes="right",
            ),
            # StatusBarCorner("top-left"),
        ]

        self.bar_content.start_children = [
            # StatusBarCorner("top-right"),
            Box(
                name="system-bar-group",
                children=[
                    self.prayer_times,
                    BarDivider(),
                    self.wallpaper_button,
                    self.clipboard_button,
                ],
                style_classes="left",
            ),
            StatusBarCorner("top-left"),
        ]
        self.bar_content.center_children = [
            StatusBarCorner("top-right"),
            CenterBox(
                name="system-bar-group",
                center_children=[self.workspaces],
                style_classes="center",
            ),
            StatusBarCorner("top-left"),
        ]

        super().__init__(
            title="fabric-bar",
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=True,
            child=self.bar_content,
        )

        # self.show_all()


class ScreenCorners:
    """
    Rounded screen corners: one small window per corner. A single
    full-screen click-through window drew the same four corners into a
    monitor-sized buffer (~14 MB at 1440p) that the compositor blended
    over everything.
    """

    def __init__(self):
        self.windows = [
            WaylandWindow(
                title="fabric-corners",
                layer="top",
                anchor=anchor,
                pass_through=True,
                visible=True,
                child=Box(
                    name="system-bar-corner",
                    children=Corner(orientation=anchor.replace(" ", "-"), size=20),  # type: ignore[arg-type]
                ),
            )
            for anchor in ("top left", "top right", "bottom left", "bottom right")
        ]
