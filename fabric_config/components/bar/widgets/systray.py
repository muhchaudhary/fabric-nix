import gi

from loguru import logger

from fabric.utils import invoke_repeater

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.revealer import Revealer

gi.require_version("Gray", "0.1")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gray, GdkPixbuf, Gtk  # noqa: E402


class SystemTrayWidget(Box):
    def __init__(self, pixel_size: int = 16, **kwargs) -> None:
        super().__init__(name="system-tray")
        self.pixel_size = pixel_size
        self.watcher = Gray.Watcher()
        self.watcher.connect("item-added", self.on_item_added)

    def on_item_added(self, _, identifier: str):
        item = self.watcher.get_item_for_identifier(identifier)
        item_button = self.do_bake_item_button(item)
        item.connect("removed", lambda *args: item_button.destroy())
        item.connect(
            "icon-changed",
            lambda icon_item: self.do_update_item_button(icon_item, item_button),
        )
        item_button.show_all()
        self.add(item_button)

    def do_update_item_button(self, item: Gray.Item, item_button: Button):
        pixmap = Gray.get_pixmap_for_pixmaps(item.get_icon_pixmaps(), 24)
        # convert the pixmap to a pixbuf
        pixbuf: GdkPixbuf.Pixbuf = (
            pixmap.as_pixbuf(self.pixel_size, GdkPixbuf.InterpType.HYPER)
            if pixmap is not None
            else Gtk.IconTheme()
            .get_default()
            .load_icon(
                item.get_icon_name(),
                self.pixel_size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
            if item.get_icon_name()
            else Gtk.IconTheme()
            .get_default()
            .load_icon(
                "application-x-executable-symbolic",
                self.pixel_size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
        )

        item_button.set_image(Image(pixbuf=pixbuf, pixel_size=self.pixel_size))

    def do_bake_item_button(self, item: Gray.Item) -> Button:
        button = Button()
        # context menu handler
        button.connect(
            "button-press-event",
            lambda button, event: self.on_button_click(button, item, event),
        )
        self.do_update_item_button(item, button)

        return button

    def on_button_click(self, button, item: Gray.Item, event):
        # for prop in item.list_properties():
        #     print(f"{prop.__doc__}: {item.get_property(prop.__doc__)}")
        match event.button:
            case 1:
                try:
                    item.activate(event.x, event.y)
                except Exception as e:
                    logger.error(e)
            case 3:
                menu = item.get_property("menu")
                menu.set_name("system-tray-menu")
                if menu:
                    menu.popup_at_widget(
                        button,
                        Gdk.Gravity.SOUTH,
                        Gdk.Gravity.NORTH,
                        event,
                    )
                else:
                    item.context_menu(event.x, event.y)


class SystemTrayRevealer(Box):
    def __init__(self, icon_size=20, **kwargs):
        self.button_image = Image(
            icon_name="pan-start-symbolic",
            icon_size=icon_size,
        )
        self.reveal_button = Button(
            image=self.button_image,
            name="panel-button",
        )

        self.revealer = Revealer(
            transition_type="slide-left",
            transition_duration=300,
            child=SystemTrayWidget(pixel_size=icon_size),
        )
        super().__init__(children=[self.revealer, self.reveal_button], **kwargs)

        self.reveal_button.connect(
            "clicked",
            lambda *args: [
                self.revealer.set_reveal_child(not self.revealer.get_reveal_child()),
                self.animate_spin(self.revealer.get_reveal_child()),
            ],
        )

    def animate_spin(self, open):
        deg = 0 if open else 180
        direction = -1 if not open else 1

        def do_animate():
            nonlocal deg
            deg += direction * 10
            self.button_image.set_style(
                f"-gtk-icon-transform: rotate({deg}deg);",
            )
            if open and deg >= 180:
                return False
            if not open and deg <= 0:
                return False
            return True

        invoke_repeater(10, do_animate)
