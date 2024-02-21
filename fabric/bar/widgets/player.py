from loguru import logger
import os
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.svg import Svg
from services.mpris import MprisPlayer
from widgets.scale import Scale
from fabric.utils.fabricator import Fabricate
from gi.repository import Gio, GLib, GObject
from fabric.utils import get_relative_path, invoke_repeater
from utls.accent import grab_color

CACHE_DIR = GLib.get_user_cache_dir() + "/fabric"
MEDIA_CACHE = CACHE_DIR + "/media"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(MEDIA_CACHE):
    os.makedirs(MEDIA_CACHE)

#TODO move Box of playerBoxes here

class playerBox(Box):
    def __init__(self, player: MprisPlayer, **kwargs):
        # TODO: create a player service DONE
        super().__init__(
            h_align="start",
            **kwargs
        )
        self.player: MprisPlayer = player
        self.exit = False
        self.player_width = 350
        self.text_wrap_width = 200
        self.image_size = 120
        self.player_height = 100
        self.cover_path = None
        self.old_cover_path = None
        self.scale_new_pos = 0

        # Exit Logic
        self.player.connect("exit", self.on_player_exit)

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
        self.player.connect("track-arturl", self.set_image)

        # Track Info 
        self.track_title = Label(label="", 
                                 name="player-title", 
                                 justfication="left",
                                 character_max_width=1,)
        self.player.connect("track-title", lambda _, x: self.track_title.set_label(x))
        
        self.track_artist = Label(label="",  
                                  name = "player-artist", 
                                  justfication="left",
                                  character_max_width=1,)
        self.player.connect("track-artist", lambda _, x: self.track_artist.set_label(x))
        
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
            style=f"min-width: {self.text_wrap_width}px;",
            children=[
                self.track_title,
                self.track_artist,
            ],
            
        )
        # Player Signals
        self.player.connect('playback-status', self.on_playback_change)
        self.player.connect('shuffle', self.shuffle_update)

        # Buttons 
        self.button_box = CenterBox(
            name = "button-box",
        )

        self.skip_next_icon = Svg(svg_file=get_relative_path("../assets/player/skip-next.svg"),
                                  name="player-icon")
        self.skip_prev_icon = Svg(svg_file=get_relative_path("../assets/player/skip-prev.svg"),
                                  name="player-icon")
        self.shuffle_icon   = Svg(svg_file=get_relative_path("../assets/player/shuffle.svg"),
                                  name="player-icon")
        self.play_icon      = Svg(svg_file=get_relative_path("../assets/player/play.svg"),
                                  name="player-icon")
        self.pause_icon     = Svg(svg_file=get_relative_path("../assets/player/pause.svg"),
                                  name="player-icon")
        
        self.play_pause_stack = Stack()
        self.play_pause_stack.add_named(self.play_icon, "play")
        self.play_pause_stack.add_named(self.pause_icon, "pause")

        self.play_pause_button = Button(name="player-button", child = self.play_pause_stack)
        self.play_pause_button.connect("clicked", lambda _: self.player.play_pause())
        self.player.connect("notify::can-pause", lambda y, _: self.play_pause_button.set_child_visible(y.can_pause))


        self.next_button = Button(name="player-button", child = self.skip_next_icon)
        self.next_button.connect("clicked", self.on_player_next)
        self.player.connect("notify::can-go-next", lambda y, _: self.next_button.set_child_visible(y.can_go_next))

        self.prev_button = Button(name="player-button", child = self.skip_prev_icon)
        self.prev_button.connect("clicked", self.on_player_prev)
        self.player.connect("notify::can-go-previous", lambda y, _: self.prev_button.set_child_visible(y.can_go_previous))

        self.shuffle_button = Button(name="player-button", child = self.shuffle_icon)
        self.shuffle_button.connect("clicked", lambda _: player.set_shuffle(not player.get_shuffle()))
        self.player.connect("notify::can-shuffle", lambda y, _: self.shuffle_button.set_child_visible(y.can_shuffle))

        self.button_box.add_center(self.play_pause_button)
        self.button_box.add_left(self.prev_button)
        self.button_box.add_left(self.shuffle_button)
        self.button_box.add_right(self.next_button)

        # Seek Bar
        self.seek_bar = Scale(
            min_value=0,
            max_value=100,
            increments=(5,5),
            orientation="h",
            draw_value=False,
            name="seek-bar",
        )
        self.seek_bar.connect("change-value", self.on_scale_move)
        self.seek_bar.connect("button-release-event",self.on_button_scale_release)
        self.player.connect("track-length", lambda _, x: self.seek_bar.set_range(0,x))
        self.player.connect("notify::can-seek", lambda y, _: self.seek_bar.set_child_visible(y.can_seek))

        self.player_info_box = Box(
            style = f"margin-left: {self.image_size + 10}px",
            v_align='center',
            h_align='start',
            orientation='v',
            children=[self.track_info,self.seek_bar, self.button_box],
        )
       
        self.inner_box = Box(
            style=f"background-color: #FEFEFE; border-radius: 20px; margin-left: {self.image_size // 2}px;" +
                  f"min-width:{self.player_width-self.image_size // 2}px; min-height:{self.player_height}px;", 
            v_align='center',
            h_align="start",
        )
        # resize the inner box 
        self.outer_box = Box(h_align="start", style=f"min-width:{self.player_width}px; min-height:{self.image_size}px;")
        self.overlay_box = Overlay(
            children=self.outer_box,
            overlays=[self.inner_box, self.player_info_box, self.image_stack]
        )
        self.add_children(self.overlay_box)
        player.initilize()
        invoke_repeater(60, self.move_seekbar)

    def on_button_scale_release(self, scale, event):
        self.player.set_position(self.scale_new_pos)
        self.exit = False
        invoke_repeater(60, self.move_seekbar)

    def on_scale_move(self, scale, event , moved_pos):
        self.exit = True
        self.scale_new_pos = moved_pos

    def on_player_exit(self, _,value):
        self.exit = value
        # del self.player sort of works but idk if has any edge cases
        self.destroy()

    def on_player_next(self, _):
        self.image_stack.set_transition_type("over-left")
        self.player.next()
    
    def on_player_prev(self, _):
        self.image_stack.set_transition_type("over-right")
        self.player.previous()


    def shuffle_update(self, player, status):
        child = self.shuffle_button.get_child()
        if status == True:
            self.shuffle_button.set_style("background-color: #eee ;box-shadow: 0 0 4px -2px black;")
            child.set_style("fill: green")
        else:
            self.shuffle_button.set_style("")
            child.set_style("fill: black")

    def on_playback_change(self, player, status):
        logger.info(f"THE prop is: {self.seek_bar.get_property('visible')}")

        if status == "paused":
            self.play_pause_button.get_child().set_visible_child_name("play")
        if status == "playing":
            self.play_pause_button.get_child().set_visible_child_name("pause")

    def img_callback(self, source: Gio.File, result: Gio.AsyncResult):
        try:
            logger.info(f"[Player] saving cover photo to {self.cover_path}")
            os.path.isfile(self.cover_path)
            # source.copy_finish(result)
            self.update_image()
        except:
            logger.error("[PLAYER] Failed to grab artUrl")

    def update_image(self):
        self.update_colors(1)
        style = lambda x: f"background-image: url('{x}'); background-size: cover; box-shadow: 0 0 4px -2px black;"
        # style2 = lambda x,y: f"background-image: cross-fade(10% url('{x}'), url('{y}')); background-size: cover;"
        # self.inner_box.set_style(style=style2(self.cover_path,get_relative_path("assets/Solid_white.png")),append=True )
        self.image_box.set_style(style=style(self.cover_path))
        self.last_image_box.set_style(style=style(self.old_cover_path))
        self.image_stack.set_visible_child_name("last_player_image")
        self.image_stack.set_visible_child_name("player_image")
    
    def update_colors(self, n):
        colors = (203,22,41)
        try:
            colors = grab_color(self.cover_path,10)
        except:
            logger.error("[PLAYER] could not grab color")
        
        bg = f"background-color: rgb{colors};"
        border = f"border-color: rgb{colors};"
        self.seek_bar.set_style(f" trough highlight{{ {bg} {border} }}")

    def set_image(self, player, url):
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
            callback = self.img_callback,
        )
    # TODO: this is bad for performance, just move by offset
    def move_seekbar(self):
        if self.player.can_seek == False or self.exit:
            return False
        self.seek_bar.set_value(self.player.get_position())
        return True
