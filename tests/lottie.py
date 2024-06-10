from typing import Literal
from rlottie_python.rlottie_wrapper import LottieAnimation

# import numpy as np
import fabric
from fabric.widgets import WaylandWindow, Box, Button, Overlay, Widget
import cairo
import gi
import ctypes

from fabric.utils import set_stylesheet_from_string

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

anim = LottieAnimation.from_file("/home/muhammad/Downloads/battery.json")
anim2 = LottieAnimation.from_file("/home/muhammad/Downloads/bolt.json")


# anim = LottieAnimation.from_file("/home/muhammad/Downloads/batter-icon-animation.json")
# TESTING this does not work for now
# anim.lottie_animation_property_override(
#     "LOTTIE_ANIMATION_PROPERTY_STROKECOLOR",
#     # "Charging.Bolt.Shape 1.Fill 1",
#     "play 3.**",
#     ctypes.c_float(0),
#     ctypes.c_float(1),
#     ctypes.c_float(0),
# )
# print(anim.tree)


# TODO make this more robust, going to needa full rewrite of all of it tbh
# TODO threading and concurency
class LottieAnimationWidget(Gtk.DrawingArea, Widget):
    def __init__(
        self,
        lottie_animation: LottieAnimation,
        scale: float = 1.0,
        do_loop: bool = False,
        draw_frame: int | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_compiled: bool = True,
        style_append: bool = False,
        style_add_brackets: bool = True,
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
        name: str | None = None,
        # size: tuple[int] | int | None = None,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(
            self,
            **(self.do_get_filtered_kwargs(kwargs)),
        )
        Widget.__init__(
            self,
            visible,
            all_visible,
            style,
            None,
            None,
            None,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            name,
            None,
        )
        # TODO: switch to just giving it a json/tgs file

        # State Management Things
        self.is_playing = False
        self.do_reverse = False
        self.curr_frame: int = 0

        self.do_loop: bool = do_loop

        self.lottie_animation: LottieAnimation = lottie_animation

        # LOTTIE STUFF
        # TODO: Error handling
        self.anim_total_duration: int = (
            self.lottie_animation.lottie_animation_get_duration()
        )
        self.anim_total_frames: int = (
            self.lottie_animation.lottie_animation_get_totalframe()
        )
        self.width, self.height = self.lottie_animation.lottie_animation_get_size()

        # TODO Does this need to be int?
        self.width = int(self.width * scale)
        self.height = int(self.height * scale)

        self.timeout_delay = int(
            (1 / self.lottie_animation.lottie_animation_get_framerate()) * 1000
        )

        # TODO switch these to loggers
        print(self.timeout_delay)
        print(self.width, self.height)

        self.set_size_request(self.width, self.height)
        self.connect("draw", self.draw)

        if self.do_loop:
            self.on_update()

    def draw(self, _: Gtk.DrawingArea, ctx: cairo.Context):
        if self.lottie_animation.async_buffer_c is not None:
            image_surface = cairo.ImageSurface.create_for_data(
                # Using this becuase the actual buffer is read only
                self.lottie_animation.async_buffer_c,
                cairo.FORMAT_ARGB32,
                self.width,
                self.height,
            )
            ctx.set_source_surface(image_surface, 0, 0)
            ctx.paint()
        return False

    def on_update(self):
        print(f"drawing frame {self.curr_frame}")
        self.is_playing = True
        self.lottie_animation.lottie_animation_render_async(
            self.curr_frame, width=self.width, height=self.height
        )

        self.lottie_animation.lottie_animation_render_flush()
        self.queue_draw()
        if self.do_reverse and self.curr_frame <= 0:
            print("done in reverse")
            # self.curr_frame = self.anim_total_frames
            self.is_playing = False
            return False if not self.do_loop else True
        elif not self.do_reverse and self.curr_frame >= self.anim_total_frames:
            print("done in normal")
            # self.curr_frame = 0
            self.is_playing = False
            return False if not self.do_loop else True
        self.curr_frame += -1 if self.do_reverse else 1

        return True

    def play_animation(self, is_reverse: bool = False):
        if self.is_playing or self.do_loop:
            return
        self.do_reverse = is_reverse
        # self.curr_frame = self.anim_total_frames if self.is_reverse else 0
        GLib.timeout_add(self.timeout_delay, self.on_update)


class LottieWindow(WaylandWindow):
    def __init__(self):
        self.lottie_button = Button(style="background-color: alpha(red, 0.0);")

        self.battery_animation = LottieAnimationWidget(
            anim,
            scale=1,
            do_loop=False,
            h_align="center",
            v_align="center",
        )
        self.bolt_animation = LottieAnimationWidget(
            anim2,
            scale=1,
            do_loop=False,
            h_align="center",
            v_align="center",
        )
        # self.animation2.set_size_request(self.animation.width, self.animation2.height)
        self.battery_animation.play_animation()
        self.bolt_animation.play_animation()
        # self.lottie_button.connect(
        #     "enter-notify-event", lambda *args: self.animation.play_animation()
        # )
        self.lottie_button.connect(
            "clicked",
            lambda *args: self.bolt_animation.play_animation(
                not self.bolt_animation.do_reverse
            ),
        )
        self.image_box = Box(
            children=Overlay(
                children=Box(
                    children=self.battery_animation,
                    style=f"min-height: {self.bolt_animation.height}px;",
                ),
                overlays=[
                    Box(children=self.bolt_animation, h_align="center"),
                    self.lottie_button,
                ],
            ),
            # style="background-color:transparent;",
        )
        super().__init__(
            layer="top",
            anchor="center",
            exclusive=False,
            style="background-color:transparent;",
            children=self.image_box,
        )


set_stylesheet_from_string("""
* {
  all: unset;
  font-family: "roboto";
  font-weight: 500;
  font-size: 15px;
  color: var(--fg);
}
""")
LottieWindow()
fabric.start()
