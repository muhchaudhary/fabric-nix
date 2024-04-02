import os
from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.svg import Svg
from services.mpris import MprisPlayer, MprisPlayerManager
from widgets.circleimage import CircleImage
from fabric.widgets.scale import Scale
from gi.repository import Gio, GLib, GObject
from utls.bezier import CubicBezier

from fabric.utils import (
    get_relative_path,
    invoke_repeater,
)
from utls.accent import grab_color

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
MEDIA_CACHE = CACHE_DIR + "/media"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(MEDIA_CACHE):
    os.makedirs(MEDIA_CACHE)


PLAYER_ASSETS_PATH = "../assets/player/"

# TODO move Box of playerBoxes here


class PlayerBoxHandler(Box):
    def __init__(self, mpris_manager: MprisPlayerManager, **kwargs):
        super().__init__(h_align="start", orientation="vertical", spacing=5, **kwargs)
        self.mpris_manager = mpris_manager
        self.mpris_manager.connect("player-appeared", self.on_new_player)
        self.mpris_manager.connect("player-vanished", self.on_lost_player)

        for player in self.mpris_manager.players:  # type: ignore
            logger.info(
                f"[PLAYER MANAGER] player found: {player.get_property('player-instance')}"
            )
            self.on_new_player(self.mpris_manager, player)

    def on_new_player(self, mpris_manager, player):
        logger.info(
            f"[PLAYER MANAGER] adding new player: {player.get_property('player-instance')}"
        )
        super().add_children(PlayerBox(player=MprisPlayer(player)))

    def on_lost_player(self, mpris_manager, player_name):
        # the playerBox is automatically removed from mprisbox children on being removed from mprismanager
        logger.info(f"[PLAYER_MANAGER] Player Removed {player_name}")


def cubic_bezier(p0, p1, p2, p3, x):
    return (
        p0 * (1 - x) ** 3
        + p1 * 3 * x * (1 - x) ** 2
        + p2 * 3 * x**2 * (1 - x)
        + p3 * x**3
    )


myBezier = CubicBezier(0.25, 0.75, 0.5, 1.25)


class PlayerBox(Box):
    def __init__(self, player: MprisPlayer, **kwargs):
        super().__init__(h_align="start", name="player-box", **kwargs)
        self.player: MprisPlayer = player
        self.exit = False
        self.player_width = 450
        self.image_size = 160
        self.player_height = 140
        self.cover_path = get_relative_path(PLAYER_ASSETS_PATH + "no_image.jpg")

        # Exit Logic
        self.player.connect("exit", self.on_player_exit)

        self.image_box = CircleImage(size=self.image_size, image_file=self.cover_path)
        self.image_stack = Box(
            h_align="start",
            v_align="start",
            style="border-radius: 100%; box-shadow: 0px 0 4px 0px black;",
        )
        self.image_stack.add_children(self.image_box)

        self.player.connect("notify::arturl", self.set_image)

        # Track Info
        self.track_title = Label(
            label="No Title",
            name="player-title",
            justfication="left",
            character_max_width=1,
        )
        self.track_artist = Label(
            label="No Artist",
            name="player-artist",
            justfication="left",
            character_max_width=1,
        )
        self.player.bind_property(
            "title",
            self.track_title,
            "label",
            GObject.BindingFlags.DEFAULT,
            lambda _, x: x if x != "" else "No Title",  # type: ignore
        )
        self.player.bind_property(
            "artist",
            self.track_artist,
            "label",
            GObject.BindingFlags.DEFAULT,
            lambda _, x: x if x != "" else "No Artist",  # type: ignore
        )

        self.track_title.set_line_wrap(True)
        self.track_title.set_xalign(0)

        self.track_artist.set_line_wrap(True)
        self.track_artist.set_xalign(0)

        self.track_info = Box(
            name="player-info",
            spacing=0,
            orientation="v",
            v_align="start",
            h_align="start",
            style=f"min-width: {self.player_width-self.image_size - 20}px;",
            children=[
                self.track_title,
                self.track_artist,
            ],
        )
        # Player Signals
        self.player.connect("notify::playback-status", self.on_playback_change)
        self.player.connect("notify::shuffle", self.shuffle_update)

        # Buttons
        self.button_box = CenterBox(
            name="button-box",
        )

        self.skip_next_icon = Svg(
            svg_file=get_relative_path(PLAYER_ASSETS_PATH + "skip-next.svg"),
            name="player-icon",
            style="fill: white",
        )
        self.skip_prev_icon = Svg(
            svg_file=get_relative_path(PLAYER_ASSETS_PATH + "skip-prev.svg"),
            name="player-icon",
            style="fill: white",
        )
        self.shuffle_icon = Svg(
            svg_file=get_relative_path(PLAYER_ASSETS_PATH + "shuffle.svg"),
            name="player-icon",
            style="fill: white",
        )
        self.play_icon = Svg(
            svg_file=get_relative_path(PLAYER_ASSETS_PATH + "play.svg"),
            name="player-icon",
            style="fill: white",
        )
        self.pause_icon = Svg(
            svg_file=get_relative_path(PLAYER_ASSETS_PATH + "pause.svg"),
            name="player-icon",
            style="fill: white",
        )

        self.play_pause_stack = Stack()
        self.play_pause_stack.add_named(self.play_icon, "play")
        self.play_pause_stack.add_named(self.pause_icon, "pause")

        self.play_pause_button = Button(
            name="player-button", child=self.play_pause_stack
        )
        self.play_pause_button.connect("clicked", lambda _: self.player.play_pause())
        self.player.bind_property("can-pause", self.play_pause_button, "visible")

        self.next_button = Button(name="player-button", child=self.skip_next_icon)
        self.next_button.connect("clicked", self.on_player_next)
        self.player.bind_property("can-go-next", self.next_button, "visible")

        self.prev_button = Button(name="player-button", child=self.skip_prev_icon)
        self.prev_button.connect("clicked", self.on_player_prev)
        self.player.bind_property("can-go-previous", self.prev_button, "visible")

        self.shuffle_button = Button(name="player-button", child=self.shuffle_icon)
        self.shuffle_button.connect("clicked", lambda _: player.toggle_shuffle())
        self.player.bind_property("can-shuffle", self.shuffle_button, "visible")

        self.button_box.add_center(self.play_pause_button)
        self.button_box.add_start(self.prev_button)
        self.button_box.add_start(self.shuffle_button)
        self.button_box.add_end(self.next_button)

        # Seek Bar
        self.seek_bar = Scale(
            min_value=0,
            max_value=100,
            increments=(5, 5),
            orientation="h",
            draw_value=False,
            name="seek-bar",
        )
        self.seek_bar.connect("change-value", self.on_scale_move)
        # self.seek_bar.connect("button-release-event", self.on_button_scale_release)
        self.player.connect(
            "notify::length",
            lambda _, x: self.seek_bar.set_range(0, self.player.length)
            if self.player.length
            else None,
        )
        self.player.bind_property("can-seek", self.seek_bar, "visible")

        self.player_info_box = Box(
            style=f"margin-left: {self.image_size + 10}px;"
            + f"min-width: {self.player_width-self.image_size - 20}px;",
            v_align="center",
            h_align="start",
            orientation="v",
            children=[self.track_info, self.seek_bar, self.button_box],
        )

        self.inner_box = Box(
            name="inner-player-box",
            style=f"margin-left: {self.image_size // 2}px;"
            + f"min-width:{self.player_width-self.image_size // 2}px;"
            + f"min-height:{self.player_height}px;",
            v_align="center",
            h_align="start",
        )
        # resize the inner box
        self.outer_box = Box(
            h_align="start",
            style=f"min-width:{self.player_width}px; min-height:{self.image_size}px;",
        )
        self.overlay_box = Overlay(
            children=self.outer_box,
            overlays=[self.inner_box, self.player_info_box, self.image_stack],
        )
        self.add_children(self.overlay_box)
        self.set_style(f"min-height:{self.image_size + 4}px")

        invoke_repeater(1000, self.move_seekbar)

    def on_scale_move(self, scale: Scale, event, moved_pos: int):
        scale.set_value(moved_pos)
        self.player.set_position(moved_pos)

    def on_player_exit(self, _, value):
        self.exit = value
        self.destroy()

    def on_player_next(self, _):
        self.image_box.set_transition_type("bezier")
        self.player.next()

    def on_player_prev(self, _):
        self.image_box.set_transition_type("negbezier")
        self.player.previous()

    def shuffle_update(self, _, __):
        child = self.shuffle_button.get_child()
        status = self.player.shuffle
        if status is True:
            child.set_style("fill: #1ED760;")  # type: ignore
        else:
            child.set_style("fill: white;")  # type: ignore

    def on_playback_change(self, player, status):
        status = self.player.playback_status
        if status == "paused":
            self.play_pause_button.get_child().set_visible_child_name("play")  # type: ignore
        if status == "playing":
            self.play_pause_button.get_child().set_visible_child_name("pause")  # type: ignore

    def img_callback(self, source: Gio.File, result: Gio.AsyncResult):
        try:
            logger.info(f"[PLAYER] saving cover photo to {self.cover_path}")
            os.path.isfile(self.cover_path)
            # source.copy_finish(result)
            if os.path.isfile(self.cover_path):
                self.update_image()
        except ValueError:
            logger.error("[PLAYER] Failed to grab artUrl")

    def update_image(self):
        self.update_colors(5)
        self.image_box.set_image(self.cover_path)
        self.rotate_animation()

    def update_colors(self, n):
        colors = (0, 0, 0)
        try:
            colors = grab_color(self.cover_path, n)
        except Exception:
            logger.error("[PLAYER] could not grab color")

        bg = f"background-color: rgb{colors};"
        border = f"border-color: rgb{colors};"
        self.seek_bar.set_style(f" trough highlight{{ {bg} {border} }}")

    def set_image(self, *args):
        url = self.player.arturl
        if url is None:
            return
        self.cover_path = (
            MEDIA_CACHE
            + "/"
            + GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1)  # type: ignore
        )
        if os.path.exists(self.cover_path):
            # messy,make it handele this better
            self.update_image()
            return
        Gio.File.new_for_uri(uri=url).copy_async(  # type: ignore
            destination=Gio.File.new_for_path(self.cover_path),
            flags=Gio.FileCopyFlags.OVERWRITE,
            io_priority=GLib.PRIORITY_DEFAULT,
            cancellable=None,
            progress_callback=None,
            callback=self.img_callback,
        )

    def rotate_animation(self):
        anim_time = 0

        def invoke():
            nonlocal anim_time
            if anim_time <= 1:
                anim_time += 0.007
                rot = 360 * myBezier.solve(anim_time)
                self.image_box.rotate_more(rot)
                return True
            self.image_box.rotate_more(0)
            return False

        invoke_repeater(16, invoke)

    def move_seekbar(self):
        if self.exit or self.player.can_seek is False:
            return False
        self.seek_bar.set_value(self.player.get_property("position"))
        return True
