from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.shapes import Corner
from gi.repository import Gdk, Gio, GLib, Gtk
from loguru import logger

from fabric_config.utils.app_search import (
    AppEntry,
    AppStats,
    calculate,
    color_formats,
    load_entries,
    match_score,
    parse_color,
    search_emoji,
)
from fabric_config.utils.color_picker import pick_color
from fabric_config.utils.hyprland_monitor import get_hyprland_monitors
from fabric_config.utils.hyprland_windows import (
    close_window,
    focus_window,
    hyprland_clients,
    kill_window,
)
from fabric_config.utils.icon_resolver import get_icon_resolver
from fabric_config.utils.units import convert
from fabric_config.utils.process import run_command_async
from fabric_config.widgets.popup_window_v2 import PopupWindow

ICON_SIZE = 32
MAX_RESULTS = 30
FREQUENT_COUNT = 6
# size of the flares joining the panel to the screen edge; keep in step
# with $appmenu-radius in _appmenu.scss
# search results glimmer in turn, this far apart
SHINE_STAGGER_MS = 20
SHINE_ROWS = 10
CORNER_SIZE = 32

HINTS = (
    "=  calc    >  run    :  emoji    ?  web    #  colour    @  windows    !  hidden"
)
WEB_SEARCH = "https://duckduckgo.com/?q={}"
# the menu's fade-out, so hyprpicker doesn't pick from it
CLOSE_DELAY_MS = 350


class ResultRow(Button):
    """One activatable line in the menu: an app, an app action, or a command."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        on_activate: Callable[[], None] | None = None,
        entry: AppEntry | None = None,
        icon_name: str | None = None,
        glyph: str | None = None,
        icon_widget: Gtk.Widget | None = None,
    ):
        self.entry = entry
        self._on_activate = on_activate
        # a window row's Hyprland address (for its context menu)
        self.address: str | None = None

        if icon_widget is not None:
            icon = icon_widget
        elif glyph is not None:
            icon = Label(glyph, name="appmenu-glyph", size=(ICON_SIZE, ICON_SIZE))
        elif entry is not None:
            icon = Image(pixbuf=entry.app.get_icon_pixbuf(size=ICON_SIZE))
        else:
            icon = Image(
                icon_name=icon_name or "application-x-executable", icon_size=24
            )
            icon.set_size_request(ICON_SIZE, ICON_SIZE)

        labels = Box(orientation="v", v_align="center", h_expand=True)
        labels.add(
            Label(
                title,
                h_align="start",
                max_chars_width=34,
                ellipsization="end",
                name="appmenu-app-name",
            )
        )
        if subtitle:
            labels.add(
                Label(
                    subtitle,
                    h_align="start",
                    max_chars_width=40,
                    ellipsization="end",
                    name="appmenu-app-desc",
                )
            )

        super().__init__(
            name="appmenu-button",
            h_expand=True,
            tooltip_text=subtitle if len(subtitle) > 40 else None,
            child=Box(spacing=12, children=[icon, labels]),
            on_clicked=lambda *_: self.activate_row(),
        )

    def activate_row(self):
        if self._on_activate:
            self._on_activate()


class AppMenu(PopupWindow):
    def __init__(self, **kwargs):
        self.stats = AppStats()
        self.entries: list[AppEntry] = []
        self._entries_dirty = True
        # rows for the full app list, built once per app and reused
        self.app_rows: dict[str, ResultRow] = {}
        # rows built for a single view, destroyed on the next refresh
        self._transient: list[Gtk.Widget] = []
        self.default_row: ResultRow | None = None
        self._shine_ids: list[int] = []
        self._shining: list[ResultRow] = []
        self._menu: Gtk.Menu | None = None

        # new or removed .desktop files
        self._app_monitor = Gio.AppInfoMonitor.get()
        self._app_monitor.connect("changed", self._on_apps_changed)

        self.search_entry = Entry(
            name="appmenu-entry",
            placeholder="Search apps",
            h_expand=True,
            on_changed=lambda *_: self.refresh(),
            on_activate=lambda *_: self.activate_default(),
        )
        self.search_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic"
        )
        self.search_entry.connect("notify::has-focus", lambda *_: self._mark_default())

        self.results_box = Box(orientation="v", spacing=2, v_align="start")
        self.scrolled_window = ScrolledWindow(
            name="appmenu-scroll",
            min_content_size=(-1, 540),
            max_content_size=(-1, 540),
            h_scrollbar_policy="never",
            child=self.results_box,
        )
        # keep the focused row in view while moving with the keyboard
        self.results_box.set_focus_vadjustment(self.scrolled_window.get_vadjustment())

        super().__init__(
            transition_duration=300,
            decorations="margin: 1px 1px 1px 0px;",
            anchor="center-left",
            transition_type="crossfade",
            child=Box(
                orientation="v",
                children=[
                    Box(
                        name="appmenu-corner",
                        children=Corner(orientation="bottom-left", size=CORNER_SIZE),
                    ),
                    Box(
                        name="appmenu",
                        orientation="v",
                        spacing=12,
                        children=[
                            self.search_entry,
                            self.scrolled_window,
                            Label(HINTS, name="appmenu-hints"),
                        ],
                    ),
                    Box(
                        name="appmenu-corner",
                        children=Corner(orientation="top-left", size=CORNER_SIZE),
                    ),
                ],
            ),
            enable_inhibitor=True,
            keyboard_mode="on-demand",
        )
        self.connect("key-press-event", self._on_key_press)

    # Data

    def _on_apps_changed(self, *_):
        self._entries_dirty = True
        if self.popup_visible:
            self._load_entries()
            self.refresh()

    def _load_entries(self):
        if not self._entries_dirty:
            return
        self.entries = load_entries()
        self.stats.migrate_legacy(self.entries)
        old_rows = self.app_rows
        self.app_rows = {}
        for entry in self.entries:
            self.app_rows[entry.id] = self._app_row(entry)
        for row in old_rows.values():
            row.destroy()
        self._entries_dirty = False

    def _entry(self, app_id: str) -> AppEntry | None:
        row = self.app_rows.get(app_id)
        return row.entry if row else None

    # Rows

    def _app_row(self, entry: AppEntry) -> ResultRow:
        row = ResultRow(
            entry.name,
            entry.description,
            on_activate=lambda: self.launch(entry),
            entry=entry,
        )
        row.connect("button-press-event", self._on_row_button_press)
        row.connect("popup-menu", lambda r: self._show_menu(r) or True)
        if entry.id in self.stats.hidden:
            row.add_style_class("hidden-app")
        return row

    def _transient_row(self, *args, **kwargs) -> ResultRow:
        row = ResultRow(*args, **kwargs)
        self._transient.append(row)
        return row

    def _transient_app_row(self, entry: AppEntry) -> ResultRow:
        row = self._app_row(entry)
        self._transient.append(row)
        return row

    def _section(self, title: str) -> Label:
        label = Label(title, name="appmenu-section", h_align="start")
        self._transient.append(label)
        return label

    def _message(self, text: str) -> Label:
        label = Label(text, name="appmenu-message", h_align="center")
        self._transient.append(label)
        return label

    # Views

    def refresh(self):
        self._stop_shine()
        self.results_box.children = []
        for widget in self._transient:
            widget.destroy()
        self._transient = []

        text = self.search_entry.get_text()
        query = text.strip()
        if not query:
            widgets = self._home_view()
        elif text.startswith("="):
            widgets = self._calc_view(text[1:].strip())
        elif text.startswith(">"):
            widgets = self._run_view(text[1:].strip())
        elif text.startswith(":"):
            widgets = self._emoji_view(text[1:])
        elif text.startswith("!"):
            widgets = self._hidden_view(text[1:].strip().lower())
        elif text.startswith("?"):
            widgets = self._web_view(text[1:].strip())
        elif text.startswith("#"):
            widgets = self._color_view(text[1:].strip())
        elif text.startswith("@"):
            widgets = self._windows_view(text[1:].strip().lower())
        else:
            widgets = self._search_view(query)

        for widget in widgets:
            self.results_box.add(widget)
        self.results_box.show_all()

        # only searches have a result worth launching on Enter
        self.default_row = (
            next((w for w in widgets if isinstance(w, ResultRow)), None)
            if query
            else None
        )
        self._mark_default()
        self.scrolled_window.get_vadjustment().set_value(0)
        if query:
            self._start_shine([w for w in widgets if isinstance(w, ResultRow)])

    def _start_shine(self, rows: list[ResultRow]):
        for i, row in enumerate(rows[:SHINE_ROWS]):
            self._shine_ids.append(
                GLib.timeout_add((i + 1) * SHINE_STAGGER_MS, self._shine, row)
            )

    def _shine(self, row: ResultRow):
        row.add_style_class("shine")
        self._shining.append(row)
        return False

    def _stop_shine(self):
        # each keystroke restarts the glimmer instead of stacking timers
        for source_id in self._shine_ids:
            GLib.source_remove(source_id)
        self._shine_ids = []
        for row in self._shining:
            row.remove_style_class("shine")
        self._shining = []

    def _home_view(self) -> list[Gtk.Widget]:
        widgets: list[Gtk.Widget] = []
        pinned = [e for i in self.stats.pinned if (e := self._entry(i))]
        if pinned:
            widgets.append(self._section("Pinned"))
            widgets += [self._transient_app_row(e) for e in pinned]

        frequent = [
            e
            for i in self.stats.top(FREQUENT_COUNT + len(pinned))
            if i not in self.stats.pinned
            and i not in self.stats.hidden
            and (e := self._entry(i))
        ][:FREQUENT_COUNT]
        if frequent:
            widgets.append(self._section("Frequent"))
            widgets += [self._transient_app_row(e) for e in frequent]

        widgets.append(self._section("All apps"))
        widgets += [
            self.app_rows[e.id] for e in self.entries if e.id not in self.stats.hidden
        ]
        return widgets

    def _search_view(self, text: str) -> list[Gtk.Widget]:
        query = text.lower()
        scored: list[tuple[float, str, Gtk.Widget]] = []
        for entry in self.entries:
            if entry.id in self.stats.hidden:
                continue
            bonus = min(8.0, self.stats.frecency(entry.id) * 2)
            score = match_score(query, entry)
            if score:
                scored.append((score + bonus, entry.name, self.app_rows[entry.id]))
            for action_id, label in entry.actions:
                action = label.lower()
                if action.startswith(query) or f" {query}" in f" {action}":
                    action_score = 65 + bonus
                elif len(query) >= 3 and query in action:
                    action_score = 45 + bonus
                else:
                    continue
                row = self._transient_row(
                    label,
                    entry.name,
                    on_activate=lambda e=entry, a=action_id: self.launch(e, a),
                    entry=entry,
                )
                scored.append((action_score, label, row))

        scored.sort(key=lambda s: (-s[0], s[1].lower()))
        widgets = [row for _, _, row in scored[:MAX_RESULTS]]

        # a bare expression like "12*4" gets an answer without the "=" prefix,
        # and "10 km to mi" a conversion (case kept: MB isn't Mb)
        if any(c.isdigit() for c in query):
            if (converted := convert(text)) is not None:
                widgets.insert(0, self._calc_row(text, converted))
            elif (
                any(c in query for c in "+-*/^%(")
                and (result := calculate(query)) is not None
            ):
                widgets.insert(0, self._calc_row(query, result))

        if not widgets:
            return [
                self._message("No matching apps"),
                self._web_row(text),
            ]
        return widgets

    def _calc_row(self, expression: str, result: str) -> ResultRow:
        # a conversion reads "6,213.7 mi"; copy just the number
        number = result.split(" ")[0].replace(",", "")
        return self._transient_row(
            f"= {result}",
            f"{expression}  ·  Enter to copy",
            on_activate=lambda: self.copy(number),
            icon_name="accessories-calculator-symbolic",
        )

    def _calc_view(self, expression: str) -> list[Gtk.Widget]:
        if not expression:
            return [
                self._message("Type an expression, e.g. =sqrt(2)*pi or =10 km to mi")
            ]
        result = convert(expression) or calculate(expression)
        if result is None:
            return [self._message("Not a valid expression")]
        return [self._calc_row(expression, result)]

    def _run_view(self, command: str) -> list[Gtk.Widget]:
        if not command:
            return [self._message("Type a command to run")]
        return [
            self._transient_row(
                command,
                "Run command",
                on_activate=lambda: self.run_command(command),
                icon_name="system-run-symbolic",
            ),
            self._transient_row(
                command,
                "Run in terminal",
                on_activate=lambda: self.run_command(command, terminal=True),
                icon_name="utilities-terminal-symbolic",
            ),
        ]

    def _emoji_view(self, query: str) -> list[Gtk.Widget]:
        if not query.strip():
            return [self._message("Type to search emoji, e.g. :heart")]
        matches = search_emoji(query)
        if not matches:
            return [self._message("No matching emoji")]
        return [
            self._transient_row(
                name.capitalize(),
                "Enter to copy",
                on_activate=lambda c=char: self.copy(c),
                glyph=char,
            )
            for char, name in matches
        ]

    def _web_row(self, query: str) -> ResultRow:
        return self._transient_row(
            f"Search the web for \u201c{query}\u201d",
            "DuckDuckGo",
            on_activate=lambda: self.open_uri(
                WEB_SEARCH.format(GLib.uri_escape_string(query, None, False))
            ),
            icon_name="web-browser-symbolic",
        )

    def _web_view(self, query: str) -> list[Gtk.Widget]:
        if not query:
            return [self._message("Type to search the web (DuckDuckGo !bangs work)")]
        widgets: list[Gtk.Widget] = []
        # something that looks like an address opens directly
        if " " not in query and "." in query.strip("."):
            url = query if "://" in query else f"https://{query}"
            widgets.append(
                self._transient_row(
                    query,
                    "Open website",
                    on_activate=lambda: self.open_uri(url),
                    icon_name="network-workgroup-symbolic",
                )
            )
        widgets.append(self._web_row(query))
        return widgets

    def _color_view(self, text: str) -> list[Gtk.Widget]:
        pick = self._transient_row(
            "Pick a colour from the screen",
            "Copies its hex code",
            on_activate=self.pick_color,
            icon_name="color-select-symbolic",
        )
        if not text:
            return [pick]
        rgb = parse_color(text)
        if rgb is None:
            return [
                self._message("Type a colour, e.g. #ff8800 or rgb(255, 136, 0)"),
                pick,
            ]
        widgets: list[Gtk.Widget] = []
        for label, value in color_formats(rgb):
            swatch = Box(
                name="appmenu-swatch",
                size=(ICON_SIZE, ICON_SIZE),
                style=f"background-color: rgb{rgb};",
            )
            widgets.append(
                self._transient_row(
                    value,
                    f"{label}  ·  Enter to copy",
                    on_activate=lambda v=value: self.copy(v),
                    icon_widget=swatch,
                )
            )
        return widgets

    def _windows_view(self, query: str) -> list[Gtk.Widget]:
        clients = sorted(hyprland_clients(), key=lambda c: c.get("focusHistoryID", 0))
        icons = get_icon_resolver()
        widgets: list[Gtk.Widget] = []
        for client in clients:
            title = client.get("title") or client.get("class") or "Window"
            app_class = client.get("class") or ""
            workspace = (client.get("workspace") or {}).get("name", "?")
            if query and query not in f"{title} {app_class}".lower():
                continue
            address = client["address"]
            row = self._transient_row(
                title,
                f"{app_class}  ·  workspace {workspace}",
                on_activate=lambda a=address: self.focus(a),
                icon_widget=Image(pixbuf=icons.get_icon_pixbuf(app_class, ICON_SIZE)),
            )
            row.address = address
            row.connect("button-press-event", self._on_row_button_press)
            row.connect("popup-menu", lambda r: self._show_menu(r) or True)
            widgets.append(row)
        if not widgets:
            return [self._message("No matching windows" if query else "No windows")]
        return widgets

    def _hidden_view(self, query: str) -> list[Gtk.Widget]:
        hidden = [e for i in self.stats.hidden if (e := self._entry(i))]
        if query:
            hidden = [e for e in hidden if match_score(query, e)]
        if not hidden:
            return [self._message("No hidden apps")]
        widgets: list[Gtk.Widget] = [self._section("Hidden — right-click to unhide")]
        return widgets + [self.app_rows[e.id] for e in hidden]

    # Selection

    def _mark_default(self):
        for row in self.app_rows.values():
            row.remove_style_class("default")
        for widget in self._transient:
            if isinstance(widget, ResultRow):
                widget.remove_style_class("default")
        if self.default_row and self.search_entry.has_focus():
            self.default_row.add_style_class("default")

    def activate_default(self):
        if self.default_row:
            self.default_row.activate_row()

    def _on_key_press(self, _, event: Gdk.EventKey):
        # typing while a row has focus goes back to the search box
        if self.search_entry.has_focus():
            return False
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        char = chr(Gdk.keyval_to_unicode(event.keyval))
        if event.keyval == Gdk.KEY_BackSpace or (char.isprintable() and char != " "):
            self.search_entry.grab_focus_without_selecting()
            self.search_entry.set_position(-1)
            return self.search_entry.event(event)
        return False

    # Context menu

    def _on_row_button_press(self, row: ResultRow, event: Gdk.EventButton):
        if event.button != 3:
            return False
        self._show_menu(row, event)
        return True

    def _show_menu(self, row: ResultRow, event: Gdk.EventButton | None = None):
        entry = row.entry
        if entry is None and row.address is None:
            return
        menu = Gtk.Menu()
        menu.get_style_context().add_class("tray")  # shared menu styling

        def add(label: str, callback: Callable[[], None]):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda *_: callback())
            menu.append(item)

        if entry is None:
            address = row.address
            assert address is not None
            add("Focus", lambda: self.focus(address))
            add("Close", lambda: self._window_action(close_window, address))
            add("Kill", lambda: self._window_action(kill_window, address))
            self._popup_menu(menu, row, event)
            return

        for action_id, label in entry.actions:
            add(label, lambda a=action_id: self.launch(entry, a))
        if entry.actions:
            menu.append(Gtk.SeparatorMenuItem())

        add("Open on new workspace", lambda: self.launch(entry, new_workspace=True))
        add(
            "Unpin" if entry.id in self.stats.pinned else "Pin to top",
            lambda: self._toggle(self.stats.pinned, entry),
        )
        add(
            "Unhide" if entry.id in self.stats.hidden else "Hide",
            lambda: self._toggle(self.stats.hidden, entry),
        )

        self._popup_menu(menu, row, event)

    def _popup_menu(
        self, menu: Gtk.Menu, row: ResultRow, event: Gdk.EventButton | None
    ):
        menu.show_all()
        # Wayland needs a parent to place the menu relative to
        menu.attach_to_widget(row, None)
        # keep a reference, or the menu is garbage collected while open
        self._menu = menu
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            # opened from the keyboard (Menu key / Shift+F10)
            menu.popup_at_widget(
                row,
                Gdk.Gravity.SOUTH_WEST,
                Gdk.Gravity.NORTH_WEST,
                Gtk.get_current_event(),
            )

    def _toggle(self, collection: list[str], entry: AppEntry):
        self.stats.toggle(collection, entry.id)
        if entry.id in self.stats.hidden:
            self.app_rows[entry.id].add_style_class("hidden-app")
        else:
            self.app_rows[entry.id].remove_style_class("hidden-app")
        self.refresh()

    # Actions

    def launch(
        self,
        entry: AppEntry,
        action: str | None = None,
        new_workspace: bool = False,
    ):
        target = f"{entry.id}:{action}" if action else entry.id
        logger.info(f"[App Menu] Launching {target}")
        if new_workspace:
            get_hyprland_monitors().send_command(
                "/dispatch hl.dsp.focus({ workspace = 'empty' })"
            )

        def on_done(success: bool, _stdout: str, stderr: str):
            if not success:
                logger.error(f"[App Menu] Failed to launch {target}: {stderr.strip()}")

        # a service unit returns once started; a scope would keep uwsm (and
        # our pipes) alive for the app's whole lifetime
        run_command_async(["uwsm", "app", "-t", "service", "--", target], on_done)
        self.stats.record_launch(entry.id)
        self.close()

    def run_command(self, command: str, terminal: bool = False):
        argv = ["uwsm", "app", "-t", "service"]
        argv += (
            ["-T", "--", "sh", "-c", command]
            if terminal
            else ["--", "sh", "-c", command]
        )

        def on_done(success: bool, _stdout: str, stderr: str):
            if not success:
                logger.error(f"[App Menu] Command failed to start: {stderr.strip()}")

        run_command_async(argv, on_done)
        self.close()

    def open_uri(self, uri: str):
        def on_done(success: bool, _stdout: str, stderr: str):
            if not success:
                logger.error(f"[App Menu] Couldn't open {uri}: {stderr.strip()}")

        run_command_async(
            ["uwsm", "app", "-t", "service", "--", "xdg-open", uri], on_done
        )
        self.close()

    def focus(self, address: str):
        focus_window(address)
        self.close()

    def _window_action(self, action: Callable[[str], None], address: str):
        action(address)
        # the window takes a moment to go; then list what's left
        GLib.timeout_add(150, lambda: self.refresh() or False)

    def pick_color(self):
        self.close()
        pick_color(CLOSE_DELAY_MS)

    def copy(self, text: str):
        run_command_async(["wl-copy", "--", text])
        self.close()

    def close(self):
        # not toggle_popup(): that moves the popup instead of hiding it when
        # the focused monitor changed since it opened
        self.popup_visible = False
        self.reveal_child.revealer.set_reveal_child(False)

    # Overrides

    def toggle_popup(self, monitor: bool | None = None):
        if not self.popup_visible:
            self._load_entries()
            self.search_entry.set_text("")
            self.refresh()
            self.search_entry.grab_focus()
        super().toggle_popup(monitor=True)
