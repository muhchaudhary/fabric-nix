from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.scale import Scale
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window


class OnScreenDisplay(Window):
    def __init__(
        self,
    ):
        self.scale_value = 0
        self.scale_max = 100

        self.osd_label = Label("0")
        self.osd_scale = Scale(
            name="osd-slider",
            h_expand=True,
            min_value=0,
            max_value=self.scale_max,
            value=50,
            notify_value=lambda*_:print("changed"),
            on_change_value=lambda scale, event, moved_pos: [
                scale.set_value(moved_pos),
                self.osd_label.set_label(str(int(moved_pos))),
            ],
        )

        self.osd_box = Box(
            name="osd-box",
            children=[
                self.osd_label,
                self.osd_scale,
                Box(
                    name="osd-end",
                    v_expand=False,
                    h_expand=False,
                ),
            ],
        )
        super().__init__(
            layer="top",
            anchor="bottom",
            child=self.osd_box,
            margin="10px 10px 10px 10px;",
        )


osd = OnScreenDisplay()


app = Application()

app.set_stylesheet_from_string("""

* {
  all: unset;
  font-family: "roboto";
  font-weight: 500;
  font-size: 15px;
  color: white;
}

#osd-box {
    border-radius: 100px;
    min-width: 250px;
    padding: 10px;
    background-color: #3F4155;
}

#osd-slider {
  margin-left: 10px;
  margin-right: 10px;
}

#osd-slider trough {
  min-height: 10px;
}

#osd-slider trough highlight {
  border-top-left-radius: 20px;
  border-bottom-left-radius: 20px;
  background-color: #D5D6EF;
}

#osd-slider slider {
  border-radius: 100%;
  min-width: 10px;
  min-height: 10px;
  background-color: #D5D6EF;
  transition: min-width 0.5s cubic-bezier(0.075, 0.82, 0.165, 1);
  transition: min-height 0.5s cubic-bezier(0.075, 0.82, 0.165, 1);
}

#osd-end {
    margin-top: 4px;
    margin-bottom: 4px;
    min-width: 10px;
    border-radius: 100%;
    background-color: #D5D6EF;
}


""")
app.run()
