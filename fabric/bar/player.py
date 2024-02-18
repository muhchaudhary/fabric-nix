from loguru import logger
import os
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.svg import Svg
from scale import Scale
from gi.repository import Gtk, Gio, Playerctl, GLib
from fabric.utils import get_relative_path

CHACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
MEDIA_CACHE = CHACHE_DIR + "/media"
if not os.path.exists(CHACHE_DIR):
    os.makedirs(CHACHE_DIR)
if not os.path.exists(MEDIA_CACHE):
    os.makedirs(MEDIA_CACHE)


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

        self.skip_next_icon = Svg(svg_file=get_relative_path("assets/player/skip-next.svg"),
                                  name="player-icon")
        self.skip_prev_icon = Svg(svg_file=get_relative_path("assets/player/skip-prev.svg"),
                                  name="player-icon")
        self.shuffle_icon   = Svg(svg_file=get_relative_path("assets/player/shuffle.svg"),
                                  name="player-icon")
        self.play_icon      = Svg(svg_file=get_relative_path("assets/player/play.svg"),
                                  name="player-icon")
        self.pause_icon     = Svg(svg_file=get_relative_path("assets/player/pause.svg"),
                                  name="player-icon")
        
        self.play_pause_stack = Stack()
        self.play_pause_stack.add_named(self.play_icon, "play")
        self.play_pause_stack.add_named(self.pause_icon, "pause")

        self.play_pause_button = Button(name="player-button", child = self.play_pause_stack)
        self.play_pause_button.connect("clicked", lambda _: self.player.play_pause())


        self.next_button = Button(name="player-button", child = self.skip_next_icon)
        self.next_button.connect("clicked", self.on_player_next)

        self.prev_button = Button(name="player-button", child = self.skip_prev_icon)
        self.prev_button.connect("clicked", self.on_player_prev)

        self.shuffle_button = Button(name="player-button", child = self.shuffle_icon)
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
                              draw_value=False,
                              name="seek-bar",
                              digits=0)
        self.seek_bar.connect("move-slider", self.scale_moved)
        self.seek_bar.connect("value-changed", self.scale_moved)
        # Connections

        self.player.connect('playback-status', self.on_playback_change)
        self.player.connect('shuffle', self.shuffle_update)
        self.player.connect("metadata", self.update)

        self.player_info_box = Box(
            style = f"margin-left: {self.image_size + 10}px",
            v_align='center',
            h_align='start',
            orientation='v',
            children=[self.track_info,self.seek_bar, self.button_box],
        )
       

        self.inner_box = Box(
            style=f"background-color: #FEFEFE; border-radius: 20px; margin-left: {self.image_size // 2}px;", 
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
        self.on_playback_change(player,player.get_property("playback-status"))
        
        

    def scale_moved(self, event):
        logger.info(("Horizontal scale is " + str(int(self.seek_bar.get_value()))))
        

    def on_player_next(self, _):
        self.image_stack.set_transition_type("over-left")
        self.player.next()
    
    def on_player_prev(self, _):
        self.image_stack.set_transition_type("over-right")
        self.player.previous()


    def shuffle_update(self, player, status):
        logger.info(f"[Player] shuffle status changed to {status}")
        child = self.shuffle_button.get_child()
        if status == True:
            self.shuffle_button.set_style("background-color: #eee ;box-shadow: 0 0 4px -2px black;")
            child.set_style("fill: green")
        else:
            self.shuffle_button.set_style("")
            child.set_style("fill: black")

    def on_playback_change(self, player, status):
        if status == Playerctl.PlaybackStatus.PAUSED:
            self.play_pause_button.get_child().set_visible_child_name("play")
        if status == Playerctl.PlaybackStatus.PLAYING:
            self.play_pause_button.get_child().set_visible_child_name("pause")

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
        self.image_box.set_style(style=style(self.cover_path))
        # self.inner_box.set_style(style=f"background-image: url('{self.cover_path}'); background-size: cover;", append=True)
        self.last_image_box.set_style(style=style(self.old_cover_path))
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

