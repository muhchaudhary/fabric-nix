from typing import Iterable, Literal
import cairo
import gi
from fabric.core import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.image import Image
from fabric.widgets.widget import Widget
from animator import (
    Animator,
    AnimatorFunction,
    EaseOutElastic,
)

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class TestWidget(Box):
    def __init__(self):
        super().__init__(
            size=(600, 300),
            name="test-name",
            children=[
                Box(h_expand=True),
                Box(
                    orientation="v",
                    children=[
                        Label("Hello Fabric", style="font-size: 32px;"),
                        Box(v_expand=True),
                        Image(icon_name="face-smile-big", icon_size=128),
                    ],
                ),
                Box(h_expand=True),
            ],
        )


class CustomRevealer(Gtk.DrawingArea, Widget):  # pyright: ignore[reportIncompatibleVariableOverride]
    def __init__(
        self,
        child: Widget,
        animator_function: AnimatorFunction,
        child_revealed: bool = False,
        transition_type: Literal["none", "crossfade"] = "none",
        transition_duration: int = 4,
        # END SPECIFIC STUFF
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        self.child = child
        self._child_revealed = child_revealed
        self.offscreen = Gtk.OffscreenWindow()
        self.offscreen.get_style_context().add_class(Gtk.STYLE_CLASS_DND)

        self.animator = Animator(
            animator_function=animator_function,
            duration=transition_duration,
            min_value=0,
            max_value=1,
            tick_widget=self,
        )
        self.animator.connect("notify::value", self.on_animate)

        Gtk.DrawingArea.__init__(self)
        Widget.__init__(
            self,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )
        self.surface = None
        self.frame = Gtk.Frame()
        self.frame.add(self.child)
        self.frame.show_all()

        self.offscreen.add(self.frame)
        self.offscreen.show()
        self.update_offscreen()

        self.connect("draw", self.on_draw)
        self.animator.play()

    def on_animate(self, animator: Animator, *_):
        self.queue_draw()

    def on_draw(self, _, cr: cairo.Context):
        cr.save()
        cr.set_source_surface(self.offscreen.get_surface(), self.animator.value, 0)
        cr.paint_with_alpha(1)
        cr.restore()

        self.set_size_request(self._width - self.animator.value, self._height)

    def update_offscreen(self):
        self.surface = self.offscreen.get_surface()
        self._width = self.surface.get_width()
        self._height = self.surface.get_height()
        self.animator.min_value = self._width
        self.animator.max_value = 0
        self.set_size_request(1, 1)


win = Window(
    layer="top",
    anchor="top right",
    child=CustomRevealer(
        child=TestWidget(),
        animator_function=EaseOutElastic(),
        transition_duration=1,
    ),
)
app = Application()
app.set_stylesheet_from_string("""
* {
all: unset;
}
#test-name {
    margin: 5px;
    background-color: #041429;
    border-color: #F4F1F8;
    border-radius: 15px;
    border-width: 2px;
    border-style: solid;
    padding: 5px;
}
""")
app.run()
