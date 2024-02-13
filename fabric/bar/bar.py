"""desktop status bar example"""
import fabric
import os
import psutil
from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.system_tray import SystemTray
from fabric.widgets.wayland import Window
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.date_time import DateTime
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from fabric.utils.string_formatter import FormattedString
from fabric.widgets.circular_progress_bar import CircularProgressBar
from fabric.hyprland.widgets import WorkspaceButton, Workspaces, ActiveWindow, Language
from service import MprisPlayerManager
from fabric.utils import (
    set_stylesheet_from_file,
    bulk_replace,
    monitor_file,
    invoke_repeater,
    get_relative_path,
)
import gi
from gi.repository import Gio, GLib, Playerctl, GdkPixbuf

PYWAL = False
AUDIO_WIDGET = True

if AUDIO_WIDGET is True:
    try:
        from fabric.audio.service import Audio
    except Exception as e:
        logger.error(e)
        AUDIO_WIDGET = False

CHACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
MEDIA_CACHE = CHACHE_DIR + "/media"
if not os.path.exists(CHACHE_DIR):
    os.makedirs(CHACHE_DIR)
if not os.path.exists(MEDIA_CACHE):
    os.makedirs(MEDIA_CACHE)


class VolumeWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audio = Audio()

        self.circular_progress_bar = CircularProgressBar(
            name="volume-circular-progress-bar",
            background_color=False,  # false = disabled
            radius_color=False,
            pie=True,
        )

        self.event_box = EventBox(
            events="scroll",
            children=Overlay(
                children=self.circular_progress_bar,
                overlays=Label(
                    label="",
                    style="margin: 0px 6px 0px 0px; font-size: 12px",  # because glyph icon is not centered
                ),
            ),
        )

        self.event_box.connect("scroll-event", self.on_scroll)
        self.audio.connect("speaker-changed", self.update)
        self.add(self.event_box)

    def on_scroll(self, widget, event):
        if event.direction == 0:
            self.audio.speaker.volume += 8
        elif event.direction == 1:
            self.audio.speaker.volume -= 8

    def update(self, *args):
        if self.audio.speaker is None:
            return
        self.circular_progress_bar.percentage = self.audio.speaker.volume
        return

class playerBox(Box):
    def __init__(self, player: Playerctl.Player, **kwargs):
        super().__init__(**kwargs)
        self.player = player
        self.player_width = 200
        self.player_hight = 100
        self.container_box = Box(
            name = "player-box", 
            spacing=10,
            )
        self.container_box.set_size_request(self.player_width, self.player_hight)

        self.image = Image()
        self.image_box = Box(
            name = "player-image",
            h_align="start",
            v_align="start",
            children=self.image,
        )

        self.track_title = Label(label="", name="player-title", justfication="left")
        self.track_artist = Label(label="",  name = "player-artist", justfication="left")
        
        self.track_title.set_line_wrap(True)
        self.track_title.set_max_width_chars(1)
        self.track_title.set_xalign(0)

        self.track_artist.set_line_wrap(True)
        self.track_artist.set_max_width_chars(1)
        self.track_artist.set_xalign(0)
        
       
        self.track_info = Box(
            name= "player-info",
            spacing= 2,
            orientation= 'v',
            v_align= "start",
            h_align= "start",
            children=[
                self.track_title,
                self.track_artist,
            ],
            
        )
        self.track_info.set_size_request(self.player_width,-1)

        self.play_pause_button = Button(
            label="Play",
            name="player-button",
        )
        
        self.player.connect('playback-status::playing', self.on_play)
        self.player.connect("metadata", self.update)
        
        #run once
        self.update(player,player.get_property("metadata"))

        self.container_box.add_children([self.image_box, self.track_info])

        self.add(self.container_box)

    def set_player(self, player):
        self.player = player
    def on_play(self, player, status):
        logger.info("[PLAYER START] on player start")
        self.play

    def play(self, *args):
        self.player.play()
    
    def pause(self, *args):
        self.player.pause()

    def img_callback(self, source: Gio.File, result: Gio.AsyncResult):
        try:
            logger.info(f"[Player] saving cover photo to {self.cover_path}")
            source.copy_finish(result)
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.cover_path,width=80,height=80)
            self.image.set_from_pixbuf(pixbuf)

        except:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.cover_path)
            logger.error(f"[PLAYER] Failed to grab artUrl {Exception}")
    
    def set_image(self, url):
        self.cover_path = MEDIA_CACHE + '/' + GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1)
        Gio.File.new_for_uri(uri=url).copy_async(
            destination = Gio.File.new_for_path(self.cover_path),
            flags = Gio.FileCopyFlags.OVERWRITE,
            io_priority = GLib.PRIORITY_DEFAULT,
            cancellable = None, 
            progress_callback = None,
            callback = self.img_callback,
        )

    def update(self, player, metadata):
        logger.info(f"[PLAYER] updating with {metadata}")
        self.set_image(metadata['mpris:artUrl'])
        self.track_title.set_label(metadata['xesam:title'])
        self.track_artist.set_label(metadata["xesam:artist"][0])


class playerWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mpris_manager = MprisPlayerManager()

        self.player_info_label = Label(label="")
        self.cover_path = ""
        self.image = Image(name='player-image')
        self.event_box = Box(
            spacing=10,
            orientation="h",
            name="hyprland-window",
            children=[
                self.player_info_label,
                self.image,
            ],
        )
        
        for player in self.mpris_manager.get_players():
            player.connect("metadata", self.update)
        self.add(self.event_box)

    def img_callback(self, source: Gio.File, result: Gio.AsyncResult):
        logger.info(f"{source}, {result.get_task_data()}")
        try:
            source.copy_finish(result)
            self.image.set_from_file(self.cover_path)

        except:
            logger.error("[PLAYER] Failed to grab artUrl")
    
    def set_image(self, url):
        self.cover_path = MEDIA_CACHE + '/' + GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1)
        Gio.File.new_for_uri(uri=url).copy_async(
            destination = Gio.File.new_for_path(self.cover_path),
            flags = Gio.FileCopyFlags.OVERWRITE,
            io_priority = GLib.PRIORITY_DEFAULT,
            cancellable = None, 
            progress_callback = None,
            callback = self.img_callback,
        )

    def get_players(self):
        return self.mpris_manager.get_players()

    def update(self, player, metadata):
        logger.info("[PLAYER] is updating")
        self.set_image(metadata["mpris:artUrl"])
        self.player_info_label.set_label(metadata["xesam:artist"][0] + "-" + metadata['xesam:title'])

class StatusBar(Window):
    def __init__(
        self,
    ):
        super().__init__(
            layer="top",
            anchor="left top right",
            margin="10px 10px -2px 10px",
            exclusive=True,
            visible=True,
        )
        self.center_box = CenterBox(name="main-window")
        self.workspaces = Workspaces(
            spacing=2,
            name="workspaces",
            buttons_list=[
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
                WorkspaceButton(label=FormattedString("")),
            ],
        )
        self.active_window = ActiveWindow(
            formatter=FormattedString(
                "{test_title(win_class)}",
                test_title=lambda x, max_length=20: "Desktop"
                if len(x) == 0
                else x
                if len(x) <= max_length
                else x[: max_length - 3] + "...",
            ),
            name="hyprland-window",
        )
        self.language = Language(
            formatter=FormattedString(
                "{replace_lang(language)}",
                replace_lang=lambda x: bulk_replace(
                    x,
                    [r".*Eng.*", r".*Ar.*"],
                    ["ENG", "ARA"],
                    regex=True,
                ),
            ),
            name="hyprland-window",
        )
        self.date_time = DateTime(name="date-time")
        self.system_tray = SystemTray(name="system-tray")
        self.ram_circular_progress_bar = CircularProgressBar(
            name="ram-circular-progress-bar",
            background_color=False,  # false = disabled
            radius_color=False,
            pie=True,
        )
        self.cpu_circular_progress_bar = CircularProgressBar(
            name="cpu-circular-progress-bar",
            background_color=False,
            radius_color=False,
            pie=True,
        )
        self.circular_progress_bars_overlay = Overlay(
            children=self.ram_circular_progress_bar,
            overlays=[
                self.cpu_circular_progress_bar,
                Label("", style="margin: 0px 6px 0px 0px; font-size: 12px"),
            ],
        )
        self.volume = VolumeWidget() if AUDIO_WIDGET is True else None
        self.mprisplayer = playerWidget()
        self.player_box = playerBox(self.mprisplayer.get_players()[0])
        self.widgets_container = Box(
            spacing=2,
            orientation="h",
            name="widgets-container",
            children=[
                self.circular_progress_bars_overlay,
            ],
        )
        self.widgets_container.add(self.volume) if self.volume is not None else None
        self.center_box.add_left(self.player_box)
        self.center_box.add_left(self.workspaces)
        self.center_box.add_right(self.widgets_container)
        self.center_box.add_center(self.active_window)
        self.center_box.add_right(self.system_tray)
        self.center_box.add_right(self.date_time)
        self.center_box.add_right(self.language)
        self.add(self.center_box)

        invoke_repeater(1000, self.update_progress_bars)
        self.update_progress_bars()  # initial call

        self.show_all()

    def update_progress_bars(self):
        self.ram_circular_progress_bar.percentage = psutil.virtual_memory().percent
        self.cpu_circular_progress_bar.percentage = psutil.cpu_percent()
        return True


def apply_style(*args):
    logger.info("[Bar] CSS applied")
    return set_stylesheet_from_file(get_relative_path("bar.css"))


if __name__ == "__main__":
    bar = StatusBar()

    if PYWAL is True:
        monitor = monitor_file(
            f"/home/{os.getlogin()}/.cache/wal/colors-widgets.css", "none"
        )
        monitor.connect("changed", apply_style)

    # initialize style
    apply_style()

    fabric.start()