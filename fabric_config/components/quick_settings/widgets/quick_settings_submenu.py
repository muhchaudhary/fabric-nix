from fabric.widgets.box import Box
from fabric.widgets.button import Button

from fabric.widgets.revealer import Revealer

from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.widget import Widget
from fabric.core.service import Signal
from fabric.utils import invoke_repeater


class QuickSubMenu(Box):
    def __init__(
        self,
        child: Widget | None,
        title: str | None = None,
        title_icon: str | None = None,
        **kwargs,
    ):
        self.title = title
        self.title_icon = title_icon
        self.child = child

        super().__init__(visible=False, **kwargs)
        self.revealer_child = Box(orientation="v", name="submenu")

        self.submenu_title_box = self.make_submenu_box()
        self.revealer_child.add(
            self.submenu_title_box
        ) if self.submenu_title_box else None
        self.revealer_child.add(self.child) if child else None

        self.revealer = Revealer(
            child=self.revealer_child, transition_type="slide-down", h_expand=True
        )
        self.revealer.connect(
            "notify::child-revealed",
            lambda rev, _: self.set_visible(rev.get_reveal_child()),
        )

        self.add(self.revealer)

        # self.revealer.set_reveal_child(True)

    def make_submenu_box(self) -> Box | None:
        if not self.title_icon and not self.title:
            return None
        submenu_box = Box(spacing=4)
        if self.title_icon:
            submenu_box.add(Image(icon_name=self.title_icon, icon_size=24))
        if self.title:
            submenu_box.add(Label(name="submenu-title-label", label=self.title))
        return submenu_box

    def do_reveal(self, visible: bool):
        self.set_visible(True)
        self.revealer.set_reveal_child(visible)

    def toggle_reveal(self) -> bool:
        self.set_visible(True)
        self.revealer.set_reveal_child(not self.revealer.get_reveal_child())
        return self.get_visible()


class QuickSubToggle(Box):
    @Signal
    def reveal_clicked(self) -> None: ...

    @Signal
    def action_clicked(self) -> None: ...

    def __init__(
        self,
        action_label: str = "My Label",
        action_icon: str = "package-x-generic-symbolic",
        pixel_size: int = 20,
        submenu: QuickSubMenu | None = None,
        **kwargs,
    ):
        self.pixel_size = pixel_size
        self.submenu = submenu

        submenu.revealer.connect(
            "notify::reveal-child",
            lambda *args: self.animate_spin(submenu.revealer.get_reveal_child()),
        ) if submenu else None

        self.button_image = Image(icon_name="pan-end-symbolic", size=20)

        self.reveal_button = Button(
            name="quicksettings-toggle-revealer", image=self.button_image
        )

        # Action button can hold an icon and a label NOTHING MORE
        self.action_icon = Image(
            name="panel-icon",
            icon_name=action_icon,
            icon_size=pixel_size,
        )
        self.action_label = Label(name="panel-text", label=action_label)
        self.action_button = Button(name="quicksettings-toggle-action")
        self.action_button.add(
            Box(
                h_align="start",
                v_align="center",
                children=[self.action_icon, self.action_label],
            )
        )

        super().__init__(
            name="quicksettings-togglebutton",
            h_align="start",
            v_align="start",
            children=[self.action_button, self.reveal_button],
            **kwargs,
        )

        self.reveal_button.connect("clicked", self.do_reveal_toggle)
        self.action_button.connect("clicked", self.do_action)

    def do_action(self, btn):
        self.emit("action-clicked")

    def do_reveal_toggle(self, btn):
        self.emit("reveal-clicked")

    def animate_spin(self, open: bool):
        deg = 0 if open else 90
        direction = -1 if not open else 1

        def do_animate():
            nonlocal deg
            deg += direction * 10
            self.button_image.set_style(
                f"-gtk-icon-transform: rotate({deg}deg);",
            )
            if open and deg >= 90:
                return False
            if not open and deg <= 0:
                return False
            return True

        invoke_repeater(10, do_animate)

    def set_active_style(self, action: bool) -> None:
        self.set_style_classes([""]) if not action else self.set_style_classes(
            ["active"]
        )

    def set_action_label(self, label: str):
        self.action_label.set_label(label)

    def set_action_icon(self, icon_name: str):
        self.action_icon.set_from_icon_name(icon_name, 1)
        self.action_icon.set_pixel_size(self.pixel_size)

    def set_pixel_size(self, pixel_size):
        self.pixel_size = pixel_size
        self.action_icon.set_pixel_size(self.pixel_size)
