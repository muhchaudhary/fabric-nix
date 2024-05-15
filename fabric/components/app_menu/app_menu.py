import subprocess

from thefuzz import fuzz, process
from widgets.popup_window import PopupWindow

from fabric.utils import get_relative_path
from fabric.utils.applications import Application, get_desktop_applications
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolled_window import ScrolledWindow


class AppButton(Button):
    def __init__(self, app: Application, **kwargs):
        self.app: Application = app
        self.app_icon = (
            Image(pixbuf=self.app.get_icon_pixbuf())
            if self.app.get_icon_pixbuf()
            else Image(icon_name="application-x-executable", pixel_size=48, icon_size=3)
        )
        self.actions_list = self.app._app.list_actions()
        self.app_name = Box(
            children=[
                Label(
                    label=self.app.display_name,
                    justfication="left",
                    ellipsization="end",
                ),
            ],
        )
        # self.app_description = Box(
        #     children=Label(
        #         label=self.app.description,
        #         justfication="left",
        #         ellipsization="end",
        #     ),
        # )
        self.button_box = Box(
            spacing=5,
            children=[
                self.app_icon,
                Box(
                    orientation="v",
                    v_align="center",
                    children=[
                        self.app_name,
                        # self.app_description,
                    ],
                ),
            ],
        )
        super().__init__(name="appmenu-button", **kwargs)
        self.connect("clicked", lambda _: self.launch_app())
        self.add(self.button_box)

    # TODO look into how ags does this
    def launch_app(self):
        cmd = [x for x in self.app.command_line.split(" ") if x[0] != "%"]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    # Unused function
    def launch_app_action(self, action: str):
        subprocess.Popen(
            self.app.command_line.split(" ") + action.split(" "),
            start_new_session=True,
        )


class AppMenu(PopupWindow):
    def __init__(self, **kwargs):
        self.scrolled_window = ScrolledWindow(
            name="appmenu-scroll",
            min_content_width=600,
            min_content_height=450,
        )
        self.applications = sorted(
            get_desktop_applications(),
            key=lambda x: x.name.lower(),
        )
        self.application_buttons = {}
        self.buttons_box = Box(orientation="v")
        self.search_app_entry = Entry(
            name="appmenu-entry",
            placeholder_text="Search for an App",
            editable=True,
            style="font-size: 30px;",
        )
        self.search_app_entry.connect("key-release-event", self.keypress)
        for app in self.applications:
            appL = AppButton(app)
            self.application_buttons[app.name] = appL
            appL.connect("clicked", lambda *args: self.toggle_popup())
            self.buttons_box.add(appL)
        self.app_names = self.application_buttons.keys()
        self.searched_buttons_box = Box(orientation="v", visible=False)
        self.scrolled_window.add_children(
            Box(
                orientation="v",
                children=[
                    self.buttons_box,
                    self.searched_buttons_box,
                ],
            ),
        )
        super().__init__(
            transition_duration=300,
            anchor="center",
            transition_type="slide-down",
            child=Box(
                name="appmenu",
                children=[
                    # This is just because im lazy btw
                    Box(
                        style="border-radius: 20px;"
                        + f" background-image: url('{get_relative_path('../../assets/app/test.png')}');"
                        + "min-width:446px; min-height:522px;",
                    ),
                    Box(
                        orientation="v",
                        children=[self.search_app_entry, self.scrolled_window],
                    ),
                ],
            ),
            enable_inhibitor=True,
            keyboard_mode="on-demand",
        )
        self.revealer.connect(
            "notify::child-revealed",
            lambda *args: self.search_app_entry.grab_focus()
            if args[0].get_child_revealed()
            else None,
        )

    def toggle_popup(self):
        self.search_app_entry.set_text("")
        self.reset_app_menu()
        super().toggle_popup()

    def keypress(self, entry: Entry, event_key):
        if event_key.get_keycode()[1] == 9:
            self.toggle_popup()
        if entry.get_text() == " " or entry.get_text() == "":
            self.reset_app_menu()
            return
        lister = process.extract(
            entry.get_text(),
            self.app_names,
            scorer=fuzz.partial_ratio,
            limit=10,
        )
        for elem_i in range(len(lister)):
            name = lister[elem_i][0]
            self.buttons_box.reorder_child(self.application_buttons[name], elem_i)

    def reset_app_menu(self):
        i = 0
        for app_button in self.application_buttons.values():
            self.buttons_box.reorder_child(app_button, i)
            i += 1


appMenu = AppMenu()
