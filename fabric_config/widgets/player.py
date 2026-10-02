import os
import threading
import urllib.request
from collections.abc import Callable
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
from gi.repository import GLib, Gtk
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
    """
    One PlayerBox per MPRIS player. Each card switches between them from the
    chip in its corner, so the switcher is part of the card.
    """

    def __init__(self, mpris_manager: MprisPlayerManager, **kwargs):
        self.player_stack = Stack(
            transition_type="slide-left-right",
            transition_duration=400,
            name="player-stack",
        )
        super().__init__(orientation="v", children=[self.player_stack])
        self.hide()

        self.mpris_manager = mpris_manager
        self.mpris_manager.connect("player-appeared", self.on_new_player)
        self.mpris_manager.connect("player-vanished", self.on_lost_player)
        for player in self.mpris_manager.players.values():  # type: ignore
            logger.info(f"[PLAYER MANAGER] player found: {player.player_name}")
            self.on_new_player(self.mpris_manager, player)

    def _boxes(self) -> List["PlayerBox"]:
        return cast(List["PlayerBox"], self.player_stack.get_children())

    def _refresh(self):
        boxes = self._boxes()
        self.set_visible(bool(boxes))
        for box in boxes:
            box.set_switchable(len(boxes) > 1)

    def switch(self, step: int):
        boxes = self._boxes()
        if len(boxes) < 2:
            return
        current = self.player_stack.get_visible_child()
        index = boxes.index(current) if current in boxes else 0  # type: ignore[arg-type]
        self.player_stack.set_visible_child(boxes[(index + step) % len(boxes)])

    def on_new_player(self, mpris_manager, player):
        logger.info(f"[PLAYER MANAGER] adding new player: {player.player_name}")
        box = PlayerBox(player, on_switch=self.switch)
        box.connect(
            "destroy", lambda *_: GLib.idle_add(lambda: self._refresh() or False)
        )
        self.player_stack.add(box)
        box.show_all()
        self._refresh()

    def on_lost_player(self, mpris_manager, bus_name):
        # the PlayerBox removes itself when its player closes; refresh after
        logger.info(f"[PLAYER_MANAGER] Player Removed {bus_name}")
        GLib.idle_add(lambda: self._refresh() or False)


def app_icon_name(player_name: str) -> str:
    """The player's symbolic icon if the theme has one, else a generic one."""
    theme = Gtk.IconTheme.get_default()
    for name in (f"{player_name}-symbolic", f"{player_name.lower()}-symbolic"):
        if theme.has_icon(name):
            return name
    return "audio-x-generic-symbolic"


# myBezier = CubicBezier(0.65, 0, 0.35, 1)


class PlayerBox(Box):
    def __init__(
        self,
        player: MprisPlayer,
        on_switch: Callable[[int], None] | None = None,
        **kwargs,
    ):
        super().__init__(h_align="start", name="player-box", **kwargs)
        self._on_switch = on_switch
        # Setup
        self.player: MprisPlayer = player
        self.cover_path = get_relative_path(PLAYER_ASSETS_PATH + "no_image.jpg")

        # tall enough for the title block, seek bar, times and controls
        self.player_height = 176
        # the album art is as tall as the card
        self.image_size = self.player_height
        self.player_width = 466

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
            v_align="center",
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
            # fill the row and ellipsize at its edge, not at a fixed length
            max_chars_width=1,
            h_expand=True,
            ellipsization="end",
            h_align="fill",
        )
        self.track_title.set_xalign(0)

        self.track_artist = Label(
            label="No Artist",
            name="player-artist",
            justfication="left",
            # fill the row and ellipsize at its edge, not at a fixed length
            max_chars_width=1,
            h_expand=True,
            ellipsization="end",
            h_align="fill",
        )
        self.track_artist.set_xalign(0)
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
                # the title gets the whole row; the compact source chip
                # (icon and switch arrows) sits at the end of the artist's
                self.track_title,
                Box(
                    spacing=8,
                    children=[self.track_artist, self._make_source_chip()],
                ),
            ],
        )
        # Player Signals
        self.player.connect("notify::playback-status", self.on_playback_change)
        self.player.connect("notify::shuffle", self.on_shuffle_update)
        self.player.connect("notify::loop-status", self.on_loop_update)

        # Buttons
        self.button_box = Box(name="button-box", h_align="center", spacing=10)

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
        minor_icon_size = 18
        self.shuffle_icon = Image(
            icon_name="media-playlist-shuffle-symbolic",
            name="player-icon",
            pixel_size=minor_icon_size,
        )
        self.loop_icon = Image(
            icon_name="media-playlist-repeat-symbolic",
            name="player-icon",
            pixel_size=minor_icon_size,
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
            style_classes=["play"],
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

        self.shuffle_button = Button(
            name="player-button", style_classes=["minor"], child=self.shuffle_icon
        )
        self.shuffle_button.connect(
            "clicked", lambda _: player.set_property("shuffle", not player.shuffle)
        )

        self.loop_button = Button(
            name="player-button", style_classes=["minor"], child=self.loop_icon
        )

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

        # shuffle, previous, play, next, repeat: one evenly spaced row; each
        # button keeps its own square size instead of stretching to the row
        for button in (
            self.shuffle_button,
            self.prev_button,
            self.play_pause_button,
            self.next_button,
            self.loop_button,
        ):
            button.set_valign(Gtk.Align.CENTER)
            button.set_halign(Gtk.Align.CENTER)
            self.button_box.add(button)

        # Seek bar: level bars driven by cava; click or drag to scrub
        self.seek_bar = LevelSeekBar(self.player, height=34)
        self.seek_bar.set_name("seek-bar")
        self.player.bind("can-seek", "visible", self.seek_bar)

        self.elapsed_label = Label(label="0:00", name="player-time", h_align="start")
        self.total_label = Label(label="0:00", name="player-time", h_align="end")
        self.time_label = CenterBox(
            start_children=self.elapsed_label, end_children=self.total_label
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

        self._inner_style = (
            f"margin-left: {self.image_size // 2 - 2}px;"
            + f"min-width:{self.player_width - self.image_size // 2}px;"
            + f"min-height:{self.player_height}px;"
        )
        self.inner_box = Box(
            name="inner-player-box",
            style_classes=["cool-border"],
            style=self._inner_style,
            v_align="center",
            h_align="start",
        )
        # resize the inner box
        self.outer_box = Box(
            h_align="start",
            style=f"min-width:{self.player_width}px;"
            f" min-height:{max(self.image_size, self.player_height)}px;",
        )
        self.overlay_box = Overlay(
            child=self.outer_box,
            overlays=[
                self.inner_box,
                self.player_info_box,
                self.image_stack,
            ],
        )
        self.children = self.children + [self.overlay_box]
        self.set_style(f"min-height:{max(self.image_size, self.player_height) + 4}px")

        self._seekbar_timer_id = invoke_repeater(1000, self.update_time_label)
        self.connect("destroy", self._on_destroy)

    def _make_source_chip(self) -> Box:
        """The player's icon and name; arrows switch players when there are several."""

        def arrow(icon: str, step: int) -> Button:
            button = Button(
                name="player-source-arrow",
                image=Image(icon_name=icon, pixel_size=10),
                v_align="center",
                on_clicked=lambda *_: (
                    self._on_switch(step) if self._on_switch else None
                ),
            )
            button.set_no_show_all(True)
            return button

        self._source_arrows = [
            arrow("pan-start-symbolic", -1),
            arrow("pan-end-symbolic", 1),
        ]
        return Box(
            name="player-source",
            h_align="end",
            v_align="center",
            spacing=4,
            children=[
                self._source_arrows[0],
                Image(
                    name="player-app-icon",
                    icon_name=app_icon_name(self.player.player_name),
                    pixel_size=12,
                ),
                self._source_arrows[1],
            ],
            tooltip_text=self.player.player_name.capitalize(),
        )

    def set_switchable(self, switchable: bool):
        for button in self._source_arrows:
            button.set_visible(switchable)

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
        on = self.player.loop_status != "None"
        self.loop_icon.style_classes = ["active"] if on else []
        (
            self.loop_button.add_style_class
            if on
            else self.loop_button.remove_style_class
        )("on")

    def on_shuffle_update(self, _, __):
        on = bool(self.player.shuffle)
        self.shuffle_icon.style_classes = ["active"] if on else []
        (
            self.shuffle_button.add_style_class
            if on
            else self.shuffle_button.remove_style_class
        )("on")

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
            self.inner_box.set_style(
                self._inner_style + f"background-image: linear-gradient(120deg,"
                f" alpha(rgb({r},{g},{b}), 0.30), alpha(rgb({r},{g},{b}), 0.04));"
            )
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
        self.elapsed_label.set_label(format_time(position))
        self.total_label.set_label(format_time(length))
        return True
