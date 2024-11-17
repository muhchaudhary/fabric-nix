import ctypes
from typing import Literal

import cairo
import gi
from rlottie_python.rlottie_wrapper import LottieAnimation, LottieAnimationProperty


from fabric.widgets.widget import Widget

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


# anim.lottie_animation_property_override(
#     LottieAnimationProperty.LOTTIE_ANIMATION_PROPERTY_FILLCOLOR,
#     "charge-state.Shape 1.Fill 1.**",
#     ctypes.c_double(1.0),
#     ctypes.c_double(1.0),
#     ctypes.c_double(0.0),
# )


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
            # **(self.do_get_filtered_kwargs(kwargs)),
        )
        Widget.__init__(
            self,
            name=name,
            visible=visible,
            all_visible=all_visible,
            style=style,
            tooltip_text=tooltip_text,
            tooltip_markup=tooltip_markup,
            h_align=h_align,
            v_align=v_align,
            h_expand=h_expand,
            v_expand=v_expand,
        )
        # TODO: switch to just giving it a json/tgs file

        # State Management Things
        self.is_playing = False
        self.do_reverse = False
        self.curr_frame: int = 0 if draw_frame is None or do_loop else draw_frame
        self.end_frame: int = lottie_animation.lottie_animation_get_totalframe()

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
        self.set_size_request(self.width, self.height)
        self.connect("draw", self.draw)
        if draw_frame is not None:
            self.on_update()

        if self.do_loop:
            GLib.timeout_add(self.timeout_delay, self.on_update)

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
        self.is_playing = True
        self.lottie_animation.lottie_animation_render_async(
            self.curr_frame, width=self.width, height=self.height
        )

        self.lottie_animation.lottie_animation_render_flush()
        self.queue_draw()
        if self.do_reverse and self.curr_frame <= self.end_frame:
            self.is_playing = False if not self.do_loop else True
            self.curr_frame = self.anim_total_frames
            return False if not self.do_loop else True
        elif not self.do_reverse and self.curr_frame >= self.end_frame:
            self.is_playing = False if not self.do_loop else True
            self.curr_frame = 0 if self.do_loop else self.curr_frame
            return self.do_loop
        self.curr_frame += -1 if self.do_reverse else 1
        return True

    def play_animation(
        self,
        start_frame: int | None = None,
        end_frame: int | None = None,
        is_reverse: bool = False,
    ):
        # TODO: check if animation can be played (santizie start and end frame inputs)
        if self.is_playing or self.do_loop:
            return
        self.do_reverse = is_reverse
        self.curr_frame = (
            start_frame
            if start_frame is not None
            else self.anim_total_frames
            if self.do_reverse
            else 0
        )
        self.end_frame = (
            end_frame if end_frame else 0 if self.do_reverse else self.anim_total_frames
        )
        # self.curr_frame = self.anim_total_frames if self.is_reverse else 0
        GLib.timeout_add(self.timeout_delay, self.on_update)
