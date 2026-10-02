import math
import os
import threading
import urllib.request
from typing import List, cast

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
from fabric.widgets.stack import Stack
from gi.repository import GLib
from loguru import logger

from fabric_config.services.mpris_v2 import MprisPlayer, MprisPlayerManager
from fabric_config.snippits.animator import Animator
from fabric_config.utils.accent import grab_accent_color_threaded
from fabric_config.widgets.level_seek_bar import LevelSeekBar, format_time
from fabric_config.utils.uri import file_uri_to_path
from fabric_config.widgets.circleimage import CircleImage

CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
MEDIA_CACHE = CACHE_DIR + "/media"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(MEDIA_CACHE):
    os.makedirs(MEDIA_CACHE)


PLAYER_ASSETS_PATH = "../assets/player/"


# TODO: implement CANCEL_ANIMATION on song skip


class PlayerBoxStack(Box):
    def __init__(self, mpris_manager: MprisPlayerManager, **kwargs):
        # The player stack
        self.player_stack = Stack(
            transition_type="slide-left-right",
            transition_duration=500,
            name="player-stack",
        )
        self.current_stack_pos = 0

        # Static buttons
        self.next_player_button = Button(
            name="panel-button",
            image=Image(icon_name="go-next-symbolic", pixel_size=24),
        )
        self.prev_player_button = Button(
            name="panel-button",
            image=Image(icon_name="go-previous-symbolic", pixel_size=24),
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
        self.player_buttons: list[Button] = []

        # Box to contain all the buttons
        self.buttons_box = CenterBox(
            start_children=self.prev_player_button,
            end_children=self.next_player_button,
        )

        super().__init__(
            orientation="v", children=[self.player_stack, self.buttons_box]
        )
        self.hide()

        self.mpris_manager = mpris_manager
        self.mpris_manager.connect("player-appeared", self.on_new_player)
        self.mpris_manager.connect("player-vanished", self.on_lost_player)
        for player in self.mpris_manager.players.values():  # type: ignore
            logger.info(
                f"[PLAYER MANAGER] player found: {player.player_name}",
            )
            self.on_new_player(self.mpris_manager, player)

    def on_player_clicked(self, type):
        # unset active from prev active button
        self.player_buttons[self.current_stack_pos].remove_style_class("active")
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
        self.player_buttons[self.current_stack_pos].add_style_class("active")
        self.player_stack.set_visible_child(
            self.player_stack.get_children()[self.current_stack_pos],
        )

    def on_new_player(self, mpris_manager, player):
        self.show()
        if len(self.player_stack.get_children()) == 0:
            self.buttons_box.hide()
        else:
            self.buttons_box.show()

        self.player_stack.children = self.player_stack.children + [PlayerBox(player)]

        self.make_new_player_button(self.player_stack.get_children()[-1])
        logger.info(
            f"[PLAYER MANAGER] adding new player: {player.player_name}",
        )
        self.player_buttons[self.current_stack_pos].style_classes = [
            "active",
            "cool-border",
        ]

    def on_lost_player(self, mpris_manager, bus_name):
        # the playerBox is automatically removed from mprisbox children on being removed from mprismanager
        # (player-vanished carries the full bus name, not the short player_name)
        logger.info(f"[PLAYER_MANAGER] Player Removed {bus_name}")
        players = cast(List[PlayerBox], self.player_stack.get_children())
        if not players:
            self.hide()
            self.current_stack_pos = 0
            return
        if len(players) == 1 and bus_name == players[0].player.bus_name:
            self.hide()
            self.current_stack_pos = 0
            return
        self.current_stack_pos = min(self.current_stack_pos, len(players) - 1)
        if players[self.current_stack_pos].player.bus_name == bus_name:
            self.current_stack_pos = max(0, self.current_stack_pos - 1)
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos],
            )
        self.player_buttons[self.current_stack_pos].style_classes = [
            "active",
            "cool-border",
        ]
        self.buttons_box.hide() if len(players) == 2 else self.buttons_box.show()

    def make_new_player_button(self, player_box):
        new_button = Button(name="player-stack-button", style_classes=["cool-border"])

        def on_player_button_click(button: Button):
            self.player_buttons[self.current_stack_pos].remove_style_class("active")
            self.current_stack_pos = self.player_buttons.index(button)
            button.add_style_class("active")
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


# myBezier = CubicBezier(0.65, 0, 0.35, 1)


class PlayerBox(Box):
    def __init__(self, player: MprisPlayer, **kwargs):
        super().__init__(h_align="start", name="player-box", **kwargs)
        # Setup
        self.player: MprisPlayer = player
        self.cover_path = get_relative_path(PLAYER_ASSETS_PATH + "no_image.jpg")

        self.player_width = 450
        self.image_size = 160
        self.player_height = 140

        # State
        self.exit = False
        self.angle_direction = 1
        self.skipped = False
        self._color_generation = 0

        # Exit Logic
        self.player.connect("closed", self.on_player_exit)

        self.image_box = CircleImage(
            size=self.image_size,
            image_file=self.cover_path,
            style="background-color: red",
        )
        self.image_stack = Box(
            children=self.image_box,
            h_align="start",
            v_align="start",
            style_classes=["cool-border"],
            style="border-radius: 100%;border-width: 2px;",
        )

        self.player.connect("notify::arturl", self.set_image)

        def do_anim(p: Animator, *_):
            self.image_box.angle = self.angle_direction * p.value

        self.art_animator = Animator(
            bezier_curve=(0, 0, 1, 1),
            duration=2,
            min_value=0,
            max_value=360,
            tick_widget=self,
            custom_curve=True,
            notify_value=do_anim,
            # on_finished=lambda *_: self.update_colors(),
        )

        # Track Info
        self.track_title = Label(
            label="No Title",
            name="player-title",
            justfication="left",
            max_chars_width=24,
            ellipsization="end",
            h_align="start",
        )
        # self.track_title.set_ellipsize(3)

        self.track_artist = Label(
            label="No Artist",
            name="player-artist",
            justfication="left",
            max_chars_width=24,
            ellipsization="end",
            h_align="start",
        )
        self.player.bind(
            "title",
            "label",
            self.track_title,
            lambda _, x: x if x != "" else "No Title",
        )
        self.player.bind(
            "artist",
            "label",
            self.track_artist,
            lambda _, x: ", ".join(x) if x != "" else "No Artist",  # type: ignore
        )

        self.track_info = Box(
            name="player-info",
            spacing=0,
            orientation="v",
            v_align="start",
            h_align="start",
            style=f"min-width: {self.player_width - self.image_size - 20}px;",
            children=[
                self.track_title,
                self.track_artist,
            ],
        )
        # Player Signals
        self.player.connect("notify::playback-status", self.on_playback_change)
        self.player.connect("notify::shuffle", self.on_shuffle_update)
        self.player.connect("notify::loop-status", self.on_loop_update)

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
        self.loop_icon = Image(
            icon_name="media-playlist-repeat-symbolic",
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
        self.player.bind("can-pause", "visible", self.play_pause_button)

        self.next_button = Button(name="player-button", child=self.skip_next_icon)
        self.next_button.connect("clicked", self.on_player_next)
        self.player.bind("can-go-next", "visible", self.next_button)

        self.prev_button = Button(name="player-button", child=self.skip_prev_icon)
        self.prev_button.connect("clicked", self.on_player_prev)
        self.player.bind("can-go-previous", "visible", self.prev_button)

        self.shuffle_button = Button(name="player-button", child=self.shuffle_icon)
        self.shuffle_button.connect(
            "clicked", lambda _: player.set_property("shuffle", not player.shuffle)
        )

        self.loop_button = Button(name="player-button", child=self.loop_icon)

        self.loop_button.connect(
            "clicked",
            lambda _: self.player.set_property(
                "loop-status",
                ["None", "Playlist", "Track"][
                    (
                        {
                            "None": 0,
                            "Playlist": 1,
                            "Track": 2,
                        }.get(player.loop_status, 0)
                        + 1
                    )
                    % 3
                ],
            ),
        )

        self.player.bind("can-control", "visible", self.shuffle_button)
        self.player.bind("can-control", "visible", self.loop_button)

        self.button_box.center_children = [self.play_pause_button]
        self.button_box.start_children = [self.prev_button, self.shuffle_button]
        self.button_box.end_children = [self.loop_button, self.next_button]

        # Seek bar: level bars driven by cava; click or drag to scrub
        self.seek_bar = LevelSeekBar(self.player)
        self.seek_bar.set_name("seek-bar")
        self.player.bind("can-seek", "visible", self.seek_bar)

        self.time_label = Label(
            label="0:00 / 0:00",
            name="player-time",
            h_align="end",
        )
        self.player.bind("can-seek", "visible", self.time_label)

        self.player_info_box = Box(
            style=f"margin-left: {self.image_size + 10}px;"
            + f"min-width: {self.player_width - self.image_size - 20}px;",
            v_align="center",
            h_align="start",
            orientation="v",
            children=[self.track_info, self.seek_bar, self.time_label, self.button_box],
        )

        self.inner_box = Box(
            name="inner-player-box",
            style_classes=["cool-border"],
            style=f"margin-left: {self.image_size // 2 - 2}px;"
            + f"min-width:{self.player_width - self.image_size // 2}px;"
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
            child=self.outer_box,
            overlays=[
                self.inner_box,
                self.player_info_box,
                self.image_stack,
                Box(
                    children=Image(
                        icon_name=f"{self.player.player_name}-symbolic", size=21
                    ),
                    h_align="end",
                    v_align="start",
                    style="margin-top: 20px; margin-right: 10px;",
                    tooltip_text=self.player.player_name,  # type: ignore
                ),
            ],
        )
        self.children = self.children + [self.overlay_box]
        self.set_style(f"min-height:{self.image_size + 4}px")

        self._seekbar_timer_id = invoke_repeater(1000, self.update_time_label)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, *_):
        # stop polling a player that has gone away
        if self._seekbar_timer_id:
            GLib.source_remove(self._seekbar_timer_id)
            self._seekbar_timer_id = 0

    def on_player_exit(self, _, value):
        self.exit = value
        self.destroy()

    def on_player_next(self, _):
        self.angle_direction = 1
        self.art_animator.pause()
        self.image_box.angle = 0
        self.player.next()

    def on_player_prev(self, _):
        self.angle_direction = -1
        self.art_animator.pause()
        self.image_box.angle = 0
        self.player.previous()

    def on_loop_update(self, _, __):
        self.loop_icon.set_from_icon_name(
            "media-playlist-repeat-symbolic"
            if self.player.loop_status != "Track"
            else "media-playlist-repeat-song-symbolic"
        )
        self.loop_icon.style_classes = (
            ["active"] if self.player.loop_status != "None" else []
        )

    def on_shuffle_update(self, _, __):
        self.shuffle_icon.style_classes = ["active"] if self.player.shuffle else []

    def on_playback_change(self, player, status):
        status = self.player.playback_status
        if status == "Paused":
            self.play_pause_button.get_child().set_visible_child_name("play")  # type: ignore
        if status == "Playing":
            self.play_pause_button.get_child().set_visible_child_name("pause")  # type: ignore

    def update_image(self):
        logger.info(f"[PLAYER] updating cover image to {self.cover_path}")
        self.image_box.set_image_from_file(self.cover_path)
        self.update_colors()

    def update_colors(self):
        colors = (255, 255, 255)
        generation = self._color_generation

        def on_accent_color(color):
            if generation != self._color_generation:
                return
            # the played part takes the art's colour, softened toward cream
            r, g, b = color if color else colors
            cream = (0xF7, 0xEF, 0xD1)
            self.seek_bar.ink = tuple(  # type: ignore[assignment]
                (c + k) / 2 / 255 for c, k in zip((r, g, b), cream)
            )
            self.seek_bar.queue_draw()
            self.art_animator.play()

        grab_accent_color_threaded(image_path=self.cover_path, callback=on_accent_color)

    def set_image(self, *args):
        url = self.player.arturl

        if url is None:
            return

        new_cover_path = (
            (
                MEDIA_CACHE
                + "/"
                + GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1)  # type: ignore
            )
            if not url.startswith("file://")
            else file_uri_to_path(url)
        )

        self._color_generation += 1

        if new_cover_path == self.cover_path:
            return

        self.cover_path = new_cover_path

        if os.path.exists(self.cover_path):
            self.update_image()
            return

        logger.info(f"[PLAYER] downloading art from {url} to {self.cover_path}")

        def download():
            try:
                urllib.request.urlretrieve(url, self.cover_path)
                GLib.idle_add(self.update_image)
            except Exception as e:
                logger.error(f"[PLAYER] Failed to download art: {e}")

        threading.Thread(target=download, daemon=True).start()

    def update_time_label(self) -> bool:
        length = self.player.length or 0
        position = self.seek_bar.position if length else 0
        self.time_label.set_label(f"{format_time(position)} / {format_time(length)}")
        return True
