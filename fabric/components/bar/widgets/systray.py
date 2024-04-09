from gi.repository import Gdk

from fabric.system_tray.service import SystemTray, SystemTrayItem
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.revealer import Revealer
from loguru import logger


class SystemTrayButton(Button):
    def __init__(self, sys_item: SystemTrayItem, icon_size=16, **kwargs):
        self._sys_item = sys_item
        self.icon_size = icon_size
        super().__init__(**kwargs)

        self._sys_item.connect("icon-changed", self.on_icon_change)
        self._sys_item.connect("status-changed", self.on_status_change)

        self.on_icon_change()
        self.connect("button-press-event", self.on_button_click)

    def on_button_click(self, button, event):
        if event.button == 1:
            try:
                self._sys_item.activate_for_event(event)
            except Exception as e:
                logger.error(e)
        elif event.button == 3:
            menu = self._sys_item.get_menu()
            menu.set_name("system-tray-menu")
            if menu:
                menu.popup_at_widget(
                    button, Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH, event
                )
            else:
                logger.error(f"Failed to find Dbusmenu for {self._sys_item.bus_name}")

    def on_icon_change(self, _=None):
        tray_icon_pixbuf = self._sys_item.get_preferred_icon_pixbuf(self.icon_size)
        self.set_image(
            Image(pixbuf=tray_icon_pixbuf)
        ) if tray_icon_pixbuf is not None else self.set_image(
            Image(icon_name="missing", pixel_size=self.icon_size)
        )

    def on_status_change(self, _, status: str):
        self.on_icon_change()


class SystemTrayBox(Box):
    def __init__(self, icon_size=16, name="system-tray", **kwargs):
        self._system_tray: SystemTray = SystemTray()
        self._system_tray.connect("item-added", self.on_item_added)
        self._system_tray.connect("item-removed", self.on_item_removed)
        self._tray_buttons = {}
        self.icon_size = icon_size
        super().__init__(name=name, **kwargs)

    def on_item_added(self, systray: SystemTray, name: str):
        tray_item: SystemTrayItem = systray.get_items()[name]
        self._tray_buttons[name] = SystemTrayButton(tray_item, self.icon_size)
        self.add_children(self._tray_buttons[name])

    def on_item_removed(self, systray: SystemTray, name: str):
        button: Button = self._tray_buttons[name]
        self.remove(button)
        button.destroy()
        self._tray_buttons.pop(name)


class SystemTrayRevealer(Box):
    def __init__(self, icon_size=20, **kwargs):
        self.icon_size = icon_size
        super().__init__(**kwargs)

        self.button_image = Image(
            icon_name="pan-start-symbolic", pixel_size=self.icon_size
        )
        self.reveal_button = Button(
            icon_image=self.button_image, name=super().get_name()
        )

        self.revealed_box = SystemTrayBox(icon_size=self.icon_size)

        self.revealer = Revealer(
            transition_type="slide-left",
            transition_duration=150,
            children=self.revealed_box,
        )
        self.add(self.revealer)
        self.add(self.reveal_button)

        self.reveal_button.connect(
            "clicked",
            lambda *args: [
                self.revealer.set_reveal_child(not self.revealer.get_reveal_child()),
                self.button_image.set_from_icon_name("pan-end-symbolic", 1)
                if self.revealer.get_reveal_child()
                else self.button_image.set_from_icon_name("pan-start-symbolic", 1),
            ],
        )
