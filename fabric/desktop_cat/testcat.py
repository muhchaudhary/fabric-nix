import fabric
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.wayland import Window
from fabric.utils import invoke_repeater, get_relative_path
import gi
import math

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf
from fabric.widgets.image import Image

TILESET_WIDTH = 4


def get_cat_pixbuf(pixbuf: GdkPixbuf.Pixbuf, x, y) -> GdkPixbuf.Pixbuf:
    return pixbuf.new_subpixbuf(x, y, 16, 16).scale_simple(
        128, 128, GdkPixbuf.InterpType.TILES
    )


def get_cat_run(pixbuf: GdkPixbuf.Pixbuf, animation_step: int, backwards: bool):
    return (
        get_cat_pixbuf(pixbuf, 2 * 16, animation_step * 16).flip(True)
        if backwards
        else get_cat_pixbuf(pixbuf, 2 * 16, animation_step * 16)
    )


class TestWindow(Window):
    def __init__(self):
        self.moving = False
        self.animating = False
        self.backwards = False

        self.cat_tileset_pixbuf: GdkPixbuf.Pixbuf = GdkPixbuf.Pixbuf.new_from_file(
            get_relative_path("../assets/CatsBlack16x16Tile.png")
        )
        self.curr_pixbuf: GdkPixbuf.Pixbuf = get_cat_pixbuf(
            self.cat_tileset_pixbuf, 16, 16
        )

        self.background_box = Box(
            style="min-width: 1920px; min-height: 1080px; background-color: alpha(red, 0.0)",
        )
        # self.background_box.pointer
        self.event_box = EventBox(
            children=self.background_box,
            events=["pointer-motion", "button-press"],
        )
        self.event_box.connect("motion-notify-event", self.on_motion_event)
        self.event_box.connect("button-press-event", self.on_button_press)
        self.cat_box = Gtk.Fixed()
        # starting cat image
        self.cat_image = Image(pixbuf=self.curr_pixbuf)
        self.cat_image_box = (
            Box(
                # style="background-color: red;",
                children=self.cat_image
            ),
        )[0]

        self.cat_box.put(
            self.cat_image_box,
            1920 // 2,
            1080 // 2,
        )
        self.background_box.add(self.cat_box)
        super().__init__(
            layer="bottom",
            anchor="top left",
            children=self.event_box,
            exclusive=False,
            style="background-color:transparent;",
            # pass_through=True,
        )
        self.show_all()

    def on_motion_event(self, _, motion):
        return
        self.cat_box.move(self.cat_image[0], motion.x + 25, motion.y + 25)

    def on_button_press(self, _, event):
        print("button type:", event.button)
        self.moving = False
        invoke_repeater(100, lambda: self.move_cat(event.x - 64, event.y - 64))

    def move_cat(self, end_x, end_y):
        self.moving = True
        self.animating = True
        x = self.cat_image.get_allocation().x
        y = self.cat_image.get_allocation().y

        angle = math.atan2(end_y - y, end_x - x)
        if -math.pi <= angle and angle < -math.pi / 2:
            self.backwards = True
        if -math.pi / 2 <= angle and angle < 0:
            self.backwards = False
        if 0 <= angle and angle < math.pi / 2:
            self.backwards = False
        if math.pi / 2 <= angle and angle < math.pi:
            self.backwards = True
        print(angle)

        def cat_mover():
            nonlocal x, y
            x += 0.5 * math.cos(angle)
            y += 0.5 * math.sin(angle)
            self.cat_box.move(self.cat_image_box, x, y)
            if not self.moving:
                self.animating = False
                return False
            if math.sqrt((end_x - x) ** 2 + (end_y - y) ** 2) > 5:
                return True
            else:
                self.animating = False
                return False

        curr_anim = 0

        def cat_animator():
            nonlocal curr_anim
            self.cat_image.set_from_pixbuf(
                get_cat_run(self.cat_tileset_pixbuf, curr_anim, self.backwards)
            )
            curr_anim = curr_anim + 1 if curr_anim != 4 else 0
            return self.animating

        invoke_repeater(1, cat_mover)
        invoke_repeater(100, cat_animator)


TestWindow()
fabric.start()
