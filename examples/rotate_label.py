from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

# Use the Animator snippit
from fabric_config.snippits.animator import Animator


class LabelWindow(Window):
    def __init__(
        self,
    ):
        self.label = Label(
            "You spin me right round, baby, right round",
            justification="center",
            h_expand=True,
            v_expand=True,
        )

        super().__init__(
            layer="top",
            anchor="center",
            style="background-color: unset",
            child=Box(size=(350, 350), children=self.label, style="border-radius: 100%; background-color: black;"),
        )

        anim = Animator(
            bezier_curve=(0, 0, 1, 1),
            duration=1,
            min_value=0,
            max_value=360,
            repeat=True,
            tick_widget=self,
            notify_value=lambda p, *_: self.label.set_angle(p.value),
        )
        anim.play()


win = LabelWindow()
app = Application()
app.run()
