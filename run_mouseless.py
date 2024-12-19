# import fabric
import string
from typing import Literal

from fabric import Application, Property
from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.widget import Widget
from gi.repository import Gdk, GLib

from fabric_config.widgets.popup_window_v2 import PopupWindow


class MouselessGridSystem(Box):
    def __init__(self, monitor_width, monitor_height, grid_size: int = 60):
        self._monitor_width = monitor_width
        self._monitor_height = monitor_height
        self.grid_elements = list(string.ascii_lowercase)
        self._grid_size = grid_size

        super().__init__(
            orientation="v",
            children=self.build_grid_system(),
            h_expand=True,
            v_expand=True,
            size=(monitor_width, monitor_height),
        )

    def build_grid_system(self):
        children = []

        total_rows = self._monitor_width // (self._grid_size)
        total_columns = self._monitor_height // (self._grid_size)

        total_rows = min(total_rows, total_columns)
        total_columns = total_rows
        for i in range(total_rows):
            second_letter = self.grid_elements[i]
            row_children = []
            for j in range(total_columns):
                first_letter = self.grid_elements[j]
                row_children.append(
                    Box(
                        h_expand=True,
                        v_expand=True,
                        children=[
                            Box(
                                h_expand=True,
                                v_expand=True,
                                name="mouseless-grid-section",
                                style_classes="first",
                                children=Label(
                                    label=second_letter.capitalize(),
                                    justification="center",
                                    h_expand=True,
                                    v_expand=True,
                                ),
                            ),
                            Box(
                                h_expand=True,
                                v_expand=True,
                                style_classes="second",
                                name="mouseless-grid-section",
                                children=Label(
                                    label=first_letter.capitalize(),
                                    justification="center",
                                    h_expand=True,
                                    v_expand=True,
                                ),
                            ),
                        ],
                    )
                )

            children.append(
                Box(
                    h_expand=True,
                    v_expand=True,
                    name="mouseless-grid-row",
                    children=row_children,
                )
            )
        return children

    @Property(int, "read-write")
    def grid_size(self):  # type: ignore
        return self._grid_size

    @grid_size.setter
    def grid_size(self, value: int):
        self._grid_size = value


class MouselessOverlay(PopupWindow):
    def __init__(self):
        self.mouseless = MouselessGridSystem(1920, 1044)
        self._first_key = None
        self._second_key = None
        self._third_key = None
        super().__init__(
            layer="overlay",
            child=self.mouseless,
            transition_type="crossfade",
            transition_duration=10,
            anchor="center",
        )

        GLib.idle_add(
            lambda: self.mouseless.set_size_request(
                self.get_allocated_width(), self.get_allocated_height()
            )
        )

        self.reveal_child.revealer.connect(
            "notify::child-revealed",
            lambda *_: GLib.timeout_add(100, self.mouse_click, "left"),
        )

    # TODO: DONT HARDCODE MONITOR SIZE!!!
    def mouse_move(self, x: int, y: int):
        exec_shell_command_async(
            f"ydotool mousemove --absolute {(x + (1920 - 1920)) / 2} {(y + (1080 - 1044)) /2}",
        )

    def mouse_click(self, click_type: Literal["left", "right", "middle"]):
        exec_shell_command_async(
            f"ydotool click { {'left': '0xC0', 'right': '0xC1', 'middle': 'OxC2'}.get(click_type) }",
        )

    def on_key_release(self, _, event_key: Gdk.EventKey):
        print(self._first_key, self._second_key, self._third_key)
        if (
            event_key.keyval == Gdk.KEY_Return
            and self._first_key is not None
            and self._second_key is not None
            and self._third_key is not None
        ):
            self.toggle_popup()
        if (
            self._first_key is not None
            and self._second_key is not None
            and self._third_key is not None
        ):
            self._reset_keys()

        key = event_key.string
        grid_elements = self.mouseless.grid_elements

        if (
            self._first_key
            and self._first_key in grid_elements[: len(self.mouseless.children)]
        ):
            if not self._second_key:
                first_key_index = grid_elements.index(self._first_key)
                self._row_children = self.mouseless.children[first_key_index].children

                self._second_key = (
                    key if key in grid_elements[: len(self._row_children)] else None
                )
            else:
                self._third_key = key
                self._handle_box_selection()

        else:
            self._first_key = (
                key if key in grid_elements[: len(self.mouseless.children)] else None
            )

        if event_key.keyval in [Gdk.KEY_Escape]:
            self._first_key = None
            self._second_key = None
            self._third_key = None
            self.toggle_popup()

    def _handle_box_selection(self):
        if self._second_key in self.mouseless.grid_elements[: len(self._row_children)]:
            second_key_index = self.mouseless.grid_elements.index(self._second_key)
            selected_box: Widget = self._row_children[second_key_index]

            if self._third_key in [
                "l",
                "r",
                "c",
            ]:
                self._move_mouse_to_box(selected_box, self._third_key)

    def _move_mouse_to_box(self, widget: Widget, position: str):
        allocation: Gdk.Rectangle = widget.get_allocation()
        x, y = allocation.x, allocation.y

        if position == "l":
            x += allocation.width // 4  # Adjust to left
        elif position == "r":
            x += 3 * allocation.width // 4  # Adjust to right
        elif position == "c":
            x += allocation.width // 2  # Center

        y += allocation.height // 2  # Vertical center
        self.mouse_move(x, y)
        self.toggle_popup()

    def _reset_keys(self):
        self._first_key = None
        self._second_key = None
        self._third_key = None

    def toggle_popup(self, monitor: bool = False):
        super().toggle_popup(monitor)


if __name__ == "__main__":
    mo = MouselessOverlay()
    mo.toggle_popup()
    app = Application()

    app.set_stylesheet_from_string("""
        * {
        all: unset;
        font-family: "roboto";
        font-weight: 500;
        font-size: 15px;
        color: white;
        }

        #mouseless-grid-section label {
        font-size: 25px;
        font-family: "roboto mono";
        }

        #mouseless-grid-section.second {
        border-style: solid solid solid dashed;
        border-width: 1px 1px 1px 0px;
        }


        #mouseless-grid-section {
        border-color: white;
        /* background-color: alpha(black, 0.1); */
        border-style: solid dashed solid dashed;
        border-width: 1px 0px 1px 0px;
        }

    """)
    app.run()
