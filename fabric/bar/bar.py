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
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from image import Image
from scale import Scale
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
from gi.repository import Gio, GLib, Playerctl, Gtk, GdkPixbuf

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
        # TODO: create a player service
        super().__init__(**kwargs)
        self.player = player
        self.player_width = 350
        self.text_wrap_width = 200
        self.image_size = 120
        self.player_height = 100
        self.cover_path = None
        self.old_cover_path = None

        # Cover Image
        self.image_box = Box(
            name = "player-image",
            h_align="start",
            v_align="start",
        )
        self.last_image_box = Box(
            name = "player-image",
            h_align="start",
            v_align="start",
        )
        self.image_box.set_size_request(self.image_size,self.image_size)
        self.last_image_box.set_size_request(self.image_size,self.image_size)
        
        self.image_stack = Stack(
            transition_duration=500,
            transition_type="over-down",
            h_align="start",
            v_align="start",
        )
        self.image_stack.add_named(self.image_box, "player_image")
        self.image_stack.add_named(self.last_image_box, "last_player_image")

        # Track Info 
        self.track_title = Label(label="", 
                                 name="player-title", 
                                 justfication="left",
                                 character_max_width=1,)
        
        self.track_artist = Label(label="",  
                                  name = "player-artist", 
                                  justfication="left",
                                  character_max_width=1,)
        
        self.track_title.set_line_wrap(True)
        self.track_title.set_xalign(0)

        self.track_artist.set_line_wrap(True)
        self.track_artist.set_xalign(0)
        
        self.track_info = Box(
            name= "player-info",
            spacing= 0,
            orientation= 'v',
            v_align= "start",
            h_align= "start",
            children=[
                self.track_title,
                self.track_artist,
            ],
            
        )
        self.track_info.set_size_request(self.text_wrap_width,-1)

        # Buttons 
        self.button_box = CenterBox(
            name = "button-box",
        )

        self.skip_next_icon = GdkPixbuf.Pixbuf.new_for_string(get_relative_path("assets/skip-next.symbolic.png"))
        self.skip_prev_icon = GdkPixbuf.Pixbuf.new_for_string(get_relative_path("assets/skip-prev.symbolic.png"))
        self.shuffle_icon   = GdkPixbuf.Pixbuf.new_for_string(get_relative_path("assets/shuffle.symbolic.png"))
        self.play_icon      = GdkPixbuf.Pixbuf.new_for_string(get_relative_path("assets/play.symbolic.png"))
        self.pause_icon     = GdkPixbuf.Pixbuf.new_for_string(get_relative_path("assets/pause.symbolic.png"))


        self.play_pause_button = Button(name="player-button", child = Image(gicon=self.play_icon, icon_size=Gtk.IconSize.BUTTON))
        self.play_pause_button.connect("clicked", lambda _: self.player.play_pause())
        
        self.next_button = Button(name="player-button", child = Image(gicon=self.skip_next_icon, icon_size=Gtk.IconSize.BUTTON) )
        self.next_button.connect("clicked", self.on_player_next)

        self.prev_button = Button(name="player-button", child = Image(gicon=self.skip_prev_icon, icon_size=Gtk.IconSize.BUTTON))
        self.prev_button.connect("clicked", self.on_player_prev)

        self.shuffle_button = Button(name="player-button", child = Image(gicon=self.shuffle_icon, icon_size=Gtk.IconSize.BUTTON))
        self.shuffle_button.connect("clicked", lambda _: player.set_shuffle(False) if player.get_property("shuffle") else player.set_shuffle(True))

        self.button_box.add_center(self.play_pause_button)
        self.button_box.add_left(self.prev_button)
        self.button_box.add_left(self.shuffle_button)
        self.button_box.add_right(self.next_button)
        # self.test_scroll = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        # Seek Bar (not working well)
        self.seek_bar = Scale(min=0,
                              max=100,
                              step=5,
                              orientation="h", 
                              draw_value=True,
                              name="seek-bar",
                              digits=0,
                              h_expand=True,
                              v_expand=True,
                              v_align="start",
                              h_align="start",
                              value_pos="bottom",
                              )
        print(self.seek_bar.get_style_context().to_string(Gtk.StyleContextPrintFlags.RECURSE))
        self.seek_bar.connect("move-slider", self.scale_moved)
        self.seek_bar.connect("value-changed", self.scale_moved)
        # Connections

        self.player.connect('playback-status', self.playback_update)
        self.player.connect('shuffle', self.shuffle_update)
        self.player.connect("metadata", self.update)

        self.player_info_box = Box(
            style = f"margin-left: {self.image_size + 10}px",
            v_align='center',
            h_align='start',
            orientation='v',
            spacing=0,
            children=[self.track_info,self.seek_bar, self.button_box],
        )
       

        self.inner_box = Box(
            style=f"background-color: #FEFEFE; border-radius: 20px; margin-left: {self.image_size // 2};", 
            v_align='center',
            h_align="start",)
        # resize the inner box 
        self.inner_box.set_size_request(self.player_width,self.player_height)

        self.outer_box = Box(h_align="start")
        self.outer_box.set_size_request(self.player_width,self.image_size)
        self.overlay_box = Overlay(
            children=self.outer_box,
            overlays=[self.inner_box, self.player_info_box, self.image_stack]
        )
        self.add_children(self.overlay_box)
        self.set_halign(Gtk.Align.START)
        self.set_size_request(self.player_width,self.image_size)
        self.update(player,player.get_property("metadata"))
        self.playback_update(player,player.get_property("playback-status"))
        
        

    def scale_moved(self, event):
        logger.info(("Horizontal scale is " + str(int(self.seek_bar.get_value()))))
        

    def on_player_next(self, _):
        self.image_stack.set_transition_type("over-right")
        self.player.next()
    
    def on_player_prev(self, _):
        self.image_stack.set_transition_type("over-left")
        self.player.previous()


    def shuffle_update(self, player, status):
        logger.info(f"[Player] shuffle status changed to {status}")
        child = self.shuffle_button.get_child()
        if status == True:
            self.shuffle_button.set_style("background-color: #eee ;box-shadow: 0 0 4px -2px black;")
            child.set_style("* {color: green}")
        else:
            self.shuffle_button.set_style("")
            child.set_style("* {color: black}")

    def playback_update(self, player, status):
        if status == Playerctl.PlaybackStatus.PAUSED:
            self.play_pause_button.get_child().set_from_gicon(self.play_icon, Gtk.IconSize.BUTTON)
        if status == Playerctl.PlaybackStatus.PLAYING:
            self.play_pause_button.get_child().set_from_gicon(self.pause_icon, Gtk.IconSize.BUTTON)

        logger.info(f"[PLAYER] status changed to {status}")

    def img_callback(self, source: Gio.File, result: Gio.AsyncResult):
        try:
            logger.info(f"[Player] saving cover photo to {self.cover_path}")
            os.path.isfile(self.cover_path)
            # source.copy_finish(result)
            self.update_image()
        except:
            logger.error("[PLAYER] Failed to grab artUrl")

    def update_image(self):
        style = lambda x: f"background-image: url('{x}'); background-size: cover; box-shadow: 0 0 2px -2px black;"
        self.image_box.set_style(style=style(self.cover_path),append=True)
        # self.inner_box.set_style(style=f"background-image: url('{self.cover_path}'); background-size: cover;", append=True)
        self.last_image_box.set_style(style=style(self.old_cover_path),append=True)
        self.image_stack.set_visible_child_name("last_player_image")
        self.image_stack.set_visible_child_name("player_image")
       

    def set_image(self, url):
        self.old_cover_path = self.cover_path
        self.cover_path = MEDIA_CACHE + '/' + GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1)
        if os.path.exists(self.cover_path):
            # messy,make it handele this better
            self.update_image()
            return
        Gio.File.new_for_uri(uri=url).copy_async(
            destination = Gio.File.new_for_path(self.cover_path),
            flags = Gio.FileCopyFlags.OVERWRITE,
            io_priority = GLib.PRIORITY_DEFAULT,
            cancellable = None, 
            progress_callback = None,
            #callback=None,
            callback = self.img_callback,

        )

    def update(self, player, metadata):
        logger.info(f"[PLAYER] playing new song")
        #self.seek_bar.set_adjustment(Gtk.Adjustment(0, 0, metadata['mpris:length'], 2e6, 2e6, 0))
        if 'mpris:artUrl' in metadata.keys():
            self.set_image(metadata['mpris:artUrl'])
        self.track_title.set_label(metadata['xesam:title'])
        self.track_artist.set_label(metadata["xesam:artist"][0])

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
        self.mprisplayer = MprisPlayerManager()
        self.mprisplayer.connect('player-appeared',self.on_new_player)
        #self.mprisplayer.connect('player-vanished', self.on_lost_player)
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
        self.center_box.add_left(self.workspaces)
        self.center_box.add_right(self.widgets_container)
        self.center_box.add_right(self.system_tray)
        self.center_box.add_right(self.date_time)
        self.center_box.add_right(self.language)
        self.center_box.add_center(self.player_box)
        self.add(self.center_box)

        invoke_repeater(1000, self.update_progress_bars)
        self.update_progress_bars()  # initial call

        self.show_all()
    
    def on_new_player(self, mpris_manager, player_manager, player,):
        logger.info(f"{player_manager}, {player}")
        self.center_box.add_left(playerBox(player=player))
    
    # def on_lost_player(self, player_manager, player):
    #     self.center_box.remove_left()

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