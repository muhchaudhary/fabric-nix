import math
import os
from typing import List

from fabric.utils import (
    get_relative_path,
    invoke_repeater,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.scale import Scale
from fabric.widgets.stack import Stack
from gi.repository import Gio, GLib, GObject
from loguru import logger

from services.mpris import MprisPlayer, MprisPlayerManager
from utils.accent import grab_color
from utils.bezier import CubicBezier
from widgets.circleimage import CircleImage

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
MEDIA_CACHE = CACHE_DIR + "/media"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(MEDIA_CACHE):
    os.makedirs(MEDIA_CACHE)


PLAYER_ASSETS_PATH = "../assets/player/"


class PlayerBoxHandler(Box):
    def __init__(self, mpris_manager: MprisPlayerManager, **kwargs):
        super().__init__(h_align="start", orientation="vertical", spacing=5, **kwargs)
        self.mpris_manager = mpris_manager
        self.mpris_manager.connect("player-appeared", self.on_new_player)
        self.mpris_manager.connect("player-vanished", self.on_lost_player)

        for player in self.mpris_manager.players:  # type: ignore
            logger.info(
                f"[PLAYER MANAGER] player found: {player.get_property('player-instance')}",
            )
            self.on_new_player(self.mpris_manager, player)

    def on_new_player(self, mpris_manager, player):
        logger.info(
            f"[PLAYER MANAGER] adding new player: {player.get_property('player-instance')}",
        )
        super().add_children(PlayerBox(player=MprisPlayer(player)))

    def on_lost_player(self, mpris_manager, player_name):
        # the playerBox is automatically removed from mprisbox children on being removed from mprismanager
        logger.info(f"[PLAYER_MANAGER] Player Removed {player_name}")


# TODO: fix lack of information on what player is current visible (add player icon)
# TODO: rewrite player_buttons_box handling
# TODO: implement CANCEL_ANIMATION on song skip


class PlayerBoxStack(Box):
    def __init__(self, mpris_manager: MprisPlayerManager, **kwargs):
        super().__init__(orientation="v")

        # The player stack
        self.player_stack = Stack(
            transition_type="slide-left-right",
            transition_duration=500,
            name="player-stack",
        )
        self.hide()
        self.current_stack_pos = 0

        # Static buttons
        self.next_player_button = Button(
            name="panel-button",
            icon_image=Image(icon_name="go-next-symbolic", pixel_size=24),
        )
        self.prev_player_button = Button(
            name="panel-button",
            icon_image=Image(icon_name="go-previous-symbolic", pixel_size=24),
        )
        self.next_player_button.connect(
            "clicked",
            lambda *args: self.on_player_clicked("next"),
        )
        self.prev_player_button.connect(
            "clicked",
            lambda *args: self.on_player_clicked("prev"),
        )

        # List to store player buttons
        self.player_buttons = []

        # Box to contain all the buttons
        self.buttons_box = CenterBox(
            start_children=self.prev_player_button,
            end_children=self.next_player_button,
        )

        self.add_children([self.player_stack, self.buttons_box])

        self.mpris_manager = mpris_manager
        self.mpris_manager.connect("player-appeared", self.on_new_player)
        self.mpris_manager.connect("player-vanished", self.on_lost_player)
        for player in self.mpris_manager.players:  # type: ignore
            logger.info(
                f"[PLAYER MANAGER] player found: {player.get_property('player-name')}",
            )
            self.on_new_player(self.mpris_manager, player)

    def on_player_clicked(self, type):
        # unset active from prev active button
        self.remove_class(self.player_buttons[self.current_stack_pos], "active")
        if type == "next":
            self.current_stack_pos = (
                self.current_stack_pos + 1
                if self.current_stack_pos != len(self.player_stack.get_children()) - 1
                else 0
            )
        elif type == "prev":
            self.current_stack_pos = (
                self.current_stack_pos - 1
                if self.current_stack_pos != 0
                else len(self.player_stack.get_children()) - 1
            )
        # set new active button
        self.add_class(self.player_buttons[self.current_stack_pos], "active")
        self.player_stack.set_visible_child(
            self.player_stack.get_children()[self.current_stack_pos],
        )

    def on_new_player(self, mpris_manager, player):
        self.show()
        if len(self.player_stack.get_children()) == 0:
            self.buttons_box.hide()
        else:
            self.buttons_box.show()
        self.player_stack.add_children(PlayerBox(player=MprisPlayer(player)))
        self.make_new_player_button(self.player_stack.get_children()[-1])
        logger.info(
            f"[PLAYER MANAGER] adding new player: {player.get_property('player-name')}",
        )
        self.player_buttons[self.current_stack_pos].set_style_classes(["active"])

    def on_lost_player(self, mpris_manager, player_name):
        # the playerBox is automatically removed from mprisbox children on being removed from mprismanager
        logger.info(f"[PLAYER_MANAGER] Player Removed {player_name}")
        players: List[PlayerBox] = self.player_stack.get_children()
        if len(players) == 1 and player_name == players[0].player.player_name:
            print("hiding please")
            self.hide()
            self.current_stack_pos = 0
            return
        if players[self.current_stack_pos].player.player_name == player_name:
            self.current_stack_pos = max(0, self.current_stack_pos - 1)
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos],
            )
        self.player_buttons[self.current_stack_pos].set_style_classes(["active"])
        self.buttons_box.hide() if len(players) == 2 else self.buttons_box.show()

    def make_new_player_button(self, player_box):
        new_button = Button(name="player-stack-button")

        def on_player_button_click(button: Button):
            self.remove_class(self.player_buttons[self.current_stack_pos], "active")
            self.current_stack_pos = self.player_buttons.index(button)
            self.add_class(button, "active")
            self.player_stack.set_visible_child(player_box)

        new_button.connect(
            "clicked",
            on_player_button_click,
        )
        self.player_buttons.append(new_button)

        # This will automatically destroy our used button
        player_box.connect(
            "destroy",
            lambda *args: [
                new_button.destroy(),  # type: ignore
                self.player_buttons.pop(self.player_buttons.index(new_button)),
            ],
        )
        self.buttons_box.add_center(self.player_buttons[-1])

    def remove_class(self, widget, class_name: str):
        GLib.idle_add(widget.get_style_context().remove_class, class_name)

    def add_class(self, widget, class_name: str):
        GLib.idle_add(widget.get_style_context().add_class, class_name)


def easeOutBounce(t: float) -> float:
    if t < 4 / 11:
        return 121 * t * t / 16
    elif t < 8 / 11:
        return (363 / 40.0 * t * t) - (99 / 10.0 * t) + 17 / 5.0
    elif t < 9 / 10:
        return (4356 / 361.0 * t * t) - (35442 / 1805.0 * t) + 16061 / 1805.0
    return (54 / 5.0 * t * t) - (513 / 25.0 * t) + 268 / 25.0


def easeInBounce(t: float) -> float:
    return 1 - easeOutBounce(1 - t)


def easeInOutBounce(t: float) -> float:
    if t < 0.5:
        return (1 - easeInBounce(1 - t * 2)) / 2
    return (1 + easeOutBounce(t * 2 - 1)) / 2


def easeOutElastic(t: float) -> float:
    c4 = (2 * math.pi) / 3
    return math.sin((t * 10 - 0.75) * c4) * math.pow(2, -10 * t) + 1


myBezier = CubicBezier(0.65, 0, 0.35, 1)


class PlayerBox(Box):
    def __init__(self, player: MprisPlayer, **kwargs):
        super().__init__(h_align="start", name="player-box", **kwargs)
        self.player: MprisPlayer = player
        self.exit = False
        self.player_width = 450
        self.image_size = 160
        self.player_height = 140
        self.cover_path = get_relative_path(PLAYER_ASSETS_PATH + "no_image.jpg")

        self.skipped = False

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
            character_max_width=24,
            ellipsization="end",
            h_align="start",
        )
        self.track_artist = Label(
            label="No Artist",
            name="player-artist",
            justfication="left",
            character_max_width=24,
            ellipsization="end",
            h_align="start",
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

        icon_size = 24
        self.skip_next_icon = Image(
            icon_name="media-skip-forward-symbolic",
            name="player-icon",
            pixel_size=icon_size,
        )
        self.skip_prev_icon = Image(
            icon_name="media-skip-backward-symbolic",
            name="player-icon",
            pixel_size=icon_size,
        )
        self.shuffle_icon = Image(
            icon_name="media-playlist-shuffle-symbolic",
            name="player-icon",
            pixel_size=icon_size,
        )
        self.play_icon = Image(
            icon_name="media-playback-start-symbolic",
            name="player-icon",
            pixel_size=icon_size,
        )
        self.pause_icon = Image(
            icon_name="media-playback-pause-symbolic",
            name="player-icon",
            pixel_size=icon_size,
        )
        self.play_pause_stack = Stack()
        self.play_pause_stack.add_named(self.play_icon, "play")
        self.play_pause_stack.add_named(self.pause_icon, "pause")

        self.play_pause_button = Button(
            name="player-button",
            child=self.play_pause_stack,
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
            lambda _, x: self.seek_bar.set_range(0, self.player.length)  # type: ignore
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
            overlays=[
                self.inner_box,
                self.player_info_box,
                self.image_stack,
                Box(
                    children=Image(
                        icon_name=f"{self.player.player_name}-symbolic", icon_size=3
                    ),
                    h_align="end",
                    v_align="start",
                    style="margin-top: 20px; margin-right: 10px;",
                    tooltip_text=self.player.player_name,  # type: ignore
                ),
            ],
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
        self.skipped = True
        self.player.next()

    def on_player_prev(self, _):
        self.image_box.set_transition_type("negbezier")
        self.skipped = True
        self.player.previous()

    def shuffle_update(self, _, __):
        child = self.shuffle_button.get_child()
        status = self.player.shuffle
        if status is True:
            child.set_style("color: #B8BB26;")  # type: ignore
        else:
            child.set_style("")  # type: ignore

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
        # TODO: lets fix this later (put in new thread)
        colors = (255, 255, 255)
        # try:
        #     colors = grab_color(self.cover_path, n)
        # except Exception:
        #     logger.error("[PLAYER] could not grab color")

        bg = f"background-color: mix(rgb{colors}, #F7EFD1, 0.5);"
        border = f"border-color: mix(rgb{colors}, #F7EFD1, 0.5);"
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

            if self.skipped and anim_time != 0:
                self.skipped = False
                return False
            else:
                self.skipped = False

            if anim_time <= 1:
                anim_time += 0.005
                rot = 360 * easeOutElastic(anim_time)
                self.image_box.rotate_more(rot)
                return True
            self.image_box.rotate_more(0)
            self.skipped = False
            return False

        invoke_repeater(16, invoke)

    def move_seekbar(self):
        if self.exit or not self.player.can_seek:
            return False
        self.seek_bar.set_value(self.player.get_property("position"))
        return True
