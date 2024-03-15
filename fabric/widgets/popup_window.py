from fabric.widgets.wayland import Window
from fabric.widgets.revealer import Revealer
from fabric.widgets.label import Label
from fabric.widgets.box import Box



class PopupWindow(Window):
    def __init__(
        self,
        child,
        transition_type: str,
        transition_duration: int,
        visible: bool = False,
        anchor: str = "top right",
        *kwargs,
    ):
        super().__init__(
            layer="overlay",
            anchor=anchor,
            all_visible=True,
            exclusive=False,
            *kwargs
        )

        self.revealer = Revealer(
            transition_type=transition_type,
            transition_duration=transition_duration,
            children=child,
        )
        self.box = Box(style="padding:1px;", children=self.revealer)
        self.visible = visible
        self.add(self.box)
        self.show_all()

    def toggle_popup(self):
        self.visible = not self.visible
        self.revealer.set_reveal_child(self.visible)
