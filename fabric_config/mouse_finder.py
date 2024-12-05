import math
from typing import TypeVar

import cairo
import gi
from fabric import Application
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow
from utils.hyprland_monitor import HyprlandWithMonitors

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

CairoSomeSurface = TypeVar("CairoSomeSurface", bound=cairo.Surface)


# Global to Gtk position
class AnimationWindow(WaylandWindow):
    def __init__(self):
        self.hyprland: HyprlandWithMonitors = HyprlandWithMonitors()
        self.drawing_area: Gtk.DrawingArea = Gtk.DrawingArea()
        self.is_cricle_drawn: bool = False

        super().__init__(
            anchor="top left bottom right",
            layer="top",
            style="background-color: transparent",
            child=Box(
                h_expand=True,
                v_expand=True,
                # children=self.fixed,
                children=self.drawing_area,
            ),
            exclusivity="none",
            keyboard_mode="none",
            pass_through=True,
            visible=True,
            all_visible=True,
        )
        self.fear_factor: float = 0
        self.cursor_x: float = 0
        self.cursor_y: float = 0
        self.cursor_r: float = 10
        self.eye_move_x: float = 0
        self.eye_move_y: float = 0
        self.drawing_area.set_size_request(
            width=self.get_allocated_width(), height=self.get_allocated_height()
        )
        self.drawing_area.connect("draw", self.on_draw)
        invoke_repeater(30, lambda: [self.get_gtk_cursor_pos(), True][1])

    def draw_eye(
        self,
        ctx: cairo.Context,
        x: float,
        y: float,
        eye_radius: float,
        sclera_radius: float,
        iris_radius: float,
        eyelid_len: float,
    ):
        distance = math.sqrt((x - self.cursor_x) ** 2 + (y - self.cursor_y) ** 2)

        if distance > eye_radius:
            scale_x = (eye_radius - sclera_radius) / distance
            scale_y = (eye_radius - sclera_radius) / distance

            self.eye_move_x = (self.cursor_x - x) * scale_x
            self.eye_move_y = (self.cursor_y - y) * scale_y

        self.fear_factor = 12 - distance // 100

        # Draw sclera (white part)
        ctx.set_source_rgb(1, 1, 1)  # White color
        ctx.arc(x + self.eye_move_x, y + self.eye_move_y, sclera_radius, 0, 2 * math.pi)
        ctx.set_line_width(10)
        ctx.stroke()

        ctx.set_source_rgb(0.5, 0.2, 0.5)  # White color
        ctx.arc(x + self.eye_move_x, y + self.eye_move_y, iris_radius, 0, 2 * math.pi)
        ctx.fill()

        # Draw upper eyelid
        eylide_width = -10 / 6
        ctx.set_line_width(10)
        ctx.stroke()

        # Draw lower eyelid
        ctx.save()
        ctx.set_source_rgb(1, 1, 1)
        ctx.move_to(x + eyelid_len, y + eylide_width)
        ctx.rel_curve_to(
            # x + eyelid_len,
            # y + eylide_width,
            0,
            0,
            -eyelid_len,
            eye_radius * 2 - eylide_width,
            -2 * eyelid_len + 2,
            -2 * eylide_width + 2,
        )  # Lower arc
        # ctx.move_to(x + eyelid_len, y - eylide_width)
        ctx.rel_curve_to(
            0,
            0,
            eyelid_len,
            -eye_radius * 2 - eylide_width,
            2 * eyelid_len ,
            2 * eylide_width,
        )  # Lower arc

        # ctx.line_to(x + eylide_width, y)

        ctx.set_line_width(10)
        ctx.stroke()
        ctx.restore()

    def on_draw(self, _, ctx: cairo.Context):
        x = self.get_allocated_width() // 2
        y = self.get_allocated_height() // 2
        eye_radius = 50
        sclera_radius = 30
        iris_radius = 20
        eyelid_len = 100

        self.draw_eye(
            ctx,
            # x + random.random() * self.fear_factor - 150,
            x - 150,
            # random.random() * self.fear_factor + y,
            y,
            eye_radius,
            sclera_radius,
            iris_radius,
            eyelid_len,
        )
        self.draw_eye(
            ctx,
            # x + random.random() * self.fear_factor + 150,
            x + 150,
            # random.random() * self.fear_factor + y,
            y,
            eye_radius,
            sclera_radius,
            iris_radius,
            eyelid_len,
        )
        # self.draw_eye(ctx, x - 200 * i, y, eye_radius, sclera_radius, iris_radius, eyelid_len)
        # self.draw_eye(ctx, x + 200 * i, y, eye_radius, sclera_radius, iris_radius, eyelid_len)

        # Draw iris (colored part)
        ctx.set_source_rgb(0, 0.5, 1)  # Blue color

    def animate_cirlce(self):
        self.drawing_area.set_size_request(
            self.get_allocated_width(), self.get_allocated_height()
        )
        self.is_cricle_drawn = True

        def on_new_value(p, *_):
            self.drawing_area.queue_draw()

        on_new_value(5)
        # def on_done_anim(*_):
        #     self.is_cricle_drawn = False

        # anim = Animator(
        #     bezier_curve=(0.42, 0, 0.58, 1),
        #     duration=0.1,
        #     min_value=0,
        #     max_value=100,
        #     tick_widget=self,
        #     notify_value=on_new_value,
        #     on_finished=on_done_anim,
        # )
        # anim.play()

    def get_gtk_cursor_pos(self):
        disp: Gdk.Display = Gdk.Display.get_default()  # type: ignore
        mon: Gdk.Monitor = disp.get_monitor(self.hyprland.get_current_gdk_monitor_id())  # type: ignore

        diff_x = mon.get_geometry().width - self.get_allocated_width()
        diff_y = mon.get_geometry().height - self.get_allocated_height()

        center_x = mon.get_geometry().width // 2
        center_y = mon.get_geometry().height // 2

        cursor_x, cursor_y = self.get_cursor_pos()

        if cursor_x - diff_x != self.cursor_x or cursor_y - diff_y != self.cursor_y:
            self.cursor_r = 50
            # do_anim = True
        else:
            self.cursor_r = 30
            # do_anim = False
        self.cursor_x = cursor_x - diff_x
        self.cursor_y = cursor_y - diff_y
        # self.cursor_r = 10
        self.drawing_area.set_size_request(
            self.get_allocated_width(), self.get_allocated_height()
        )
        self.eye_move_x = self.cursor_x - center_x
        self.eye_move_y = self.cursor_y - center_y
        self.drawing_area.queue_draw()

    def get_cursor_pos(self):
        self.hyprland.get_current_gdk_monitor_id()
        a = self.hyprland.send_command("cursorpos")
        return tuple(int(x) for x in a.reply.decode("utf8").split(","))


animated_window = AnimationWindow()
app = Application()
app.run()
