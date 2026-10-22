from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

import fabric_config.config as config


class KeyboardIndicator(Box):
    """
    Caps Lock while it's on, and the layout when there's more than one (click
    to switch). Hidden when neither applies.
    """

    def __init__(self, **kwargs):
        self.service = config.keyboard
        self.caps_icon = Image(
            name="keyboard-caps-icon",
            icon_name="keyboard-caps-locked-symbolic",
            icon_size=16,
            tooltip_text="Caps Lock is on",
        )
        self.layout_label = Label(name="keyboard-layout-label")
        self.layout_button = Button(
            style_classes=["button-basic", "button-basic-props", "button-border"],
            name="keyboard-layout",
            child=self.layout_label,
            on_clicked=lambda *_: self.service.next_layout(),
        )
        super().__init__(
            name="keyboard-indicator",
            spacing=4,
            children=[self.caps_icon, self.layout_button],
            **kwargs,
        )
        for widget in (self, self.caps_icon, self.layout_button):
            # stay hidden through the bar's show_all()
            widget.set_no_show_all(True)
        for prop in ("caps-lock", "layouts", "layout-name"):
            self.service.connect(f"notify::{prop}", lambda *_: self.sync())
        self.sync()

    def sync(self):
        caps = self.service.caps_lock
        several = len(self.service.layouts) > 1
        self.caps_icon.set_visible(caps)
        self.layout_label.set_label(self.service.layout_code)
        self.layout_button.set_tooltip_text(
            f"{self.service.layout_name}\nClick to switch layout"
        )
        self.layout_button.set_visible(several)
        self.set_visible(caps or several)
