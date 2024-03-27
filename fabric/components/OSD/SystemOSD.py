import os
import config
from fabric.widgets.box import Box
from fabric.utils import monitor_file
from fabric.widgets.image import Image
from widgets.popup_window import PopupWindow

class SystemOSD(PopupWindow):
    def __init__(self, **kwargs):
        self.max_brightness = int(
            os.read(
                os.open(
                    "/sys/class/backlight/intel_backlight/max_brightness", os.O_RDONLY
                ),
                20,
            )
        )
        self.brightness = 0
        self.vol = 0

        self.monitor = monitor_file(
            "/sys/class/backlight/intel_backlight/brightness", "none"
        )

        self.overlay_fill_box = Box()
        self.icon = Image()

        config.audio.connect("speaker-changed", self.update_label_audio)
        self.monitor.connect("changed", self.update_label_brightness)

        super().__init__(
            transition_duration=100,
            anchor="right",
            transition_type="slide-left",
            child=Box(
                name="quicksettings",
                orientation="v",
                children=[self.overlay_fill_box, self.icon],
                style="margin-right: 10px;",
            ),
            **kwargs,
        )

    def update_label_audio(self, _):
        icon_name = "-".join(str(config.audio.speaker.icon).split("-")[0:2])
        self.icon.set_from_icon_name(icon_name + "-symbolic", 6)
        if self.vol == config.audio.speaker.volume or config.inhibit_overlay:
            return
        self.vol = config.audio.speaker.volume
        self.overlay_fill_box.set_style(
            "min-width: 25px; min-height: 200px;"
            + f"background-image: linear-gradient(to top, #64D9FF {round(self.vol)}%, #303030 {round(self.vol)}%);"
            + "border-radius: 200px; padding-right: 15px; margin-bottom:5px;"
        )
        self.popup_timeout()

    def update_label_brightness(self, _, file, *args):
        new_brightness = round(
            int(file.load_bytes()[0].get_data()) / int(self.max_brightness) * 100
        )
        if self.brightness == new_brightness or config.inhibit_overlay:
            return
        self.icon.set_from_icon_name("display-brightness-symbolic", 6)
        self.brightness = new_brightness
        self.overlay_fill_box.set_style(
            "min-width: 25px; min-height: 200px;"
            + f"background-image: linear-gradient(to top, #64D9FF {self.brightness}%, #303030 {self.brightness}%);"
            + "border-radius: 200px; padding-right: 15px; margin-bottom:5px;"
        )
        self.popup_timeout()
