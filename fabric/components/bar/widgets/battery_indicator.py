import datetime
import psutil

from fabric.core.fabricator import Fabricator
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.overlay import Overlay
from tests.lottie import LottieAnimationWidget, LottieAnimation


class BatteryIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(v_align="center", h_align="start", **kwargs)
        if not psutil.sensors_battery():
            self.set_visible(False)
            return

        self.is_charging = None
        self.curr_percent = None
        battery = LottieAnimation.from_file("/home/muhammad/Downloads/battery.json")
        bolt = LottieAnimation.from_file("/home/muhammad/Downloads/bolt.json")

        self.battery_animation = LottieAnimationWidget(
            battery,
            scale=0.25,
            do_loop=False,
            h_align="center",
            v_align="center",
        )
        self.bolt_animation = LottieAnimationWidget(
            bolt,
            scale=0.25,
            do_loop=False,
            h_align="center",
            v_align="center",
        )

        self.lottie_button = Button(name="panel-button")

        self.battery = Fabricator(
            poll_from=self.poll_batt, interval=1000, on_changed=self.update_battery
        )

        self.lottie_battery_box = Box(
            children=Overlay(
                child=Box(
                    children=self.battery_animation,
                    style=f"min-height: {self.bolt_animation.height}px;",
                    h_align="center",
                    v_align="center",
                ),
                overlays=[
                    Box(children=self.bolt_animation, h_align="center"),
                ],
            ),
        )

        self.battery_icon = Image(name="battery-icon")
        self.current_class = ""
        self.battery_percent = Label(name="battery-label")

        self.battery_percent_revealer = Revealer(
            child=self.battery_percent,
            transition_type="slide-left",
        )

        # self.buttons = Button(
        #     name="panel-button",
        # )
        self.lottie_button.add(
            Box(children=[self.battery_percent_revealer, self.lottie_battery_box])
        )

        self.lottie_button.connect(
            "clicked",
            lambda *args: self.battery_percent_revealer.set_reveal_child(
                not self.battery_percent_revealer.get_child_revealed(),
            ),
        )

        self.add(self.lottie_button)

    def update_battery(self, _, value):
        percent = value.percent
        secsleft = value.secsleft
        charging = value.power_plugged
        self.battery_percent.set_label(str(int(round(percent))) + "%")

        self.lottie_button.set_tooltip_text(
            str(int(round(percent)))
            + "% "
            + str(datetime.timedelta(seconds=secsleft))
            + " left",
        ) if not charging else self.lottie_button.set_tooltip_text(
            str(int(round(percent))) + "% " + "Charging",
        )

        if int(percent) != self.curr_percent:
            self.curr_percent = int(percent)
            do_reverse: bool = (
                True
                if int(percent * 1.5) < self.battery_animation.curr_frame
                else False
            )
            self.battery_animation.play_animation(
                is_reverse=do_reverse,
                start_frame=max(int(percent * 1.5), self.battery_animation.curr_frame)
                if do_reverse
                else min(int(percent * 1.5), self.battery_animation.curr_frame),
                end_frame=int(percent * 1.5),
            )
        self.battery_icon.set_pixel_size(28)

        if self.is_charging != charging:
            self.is_charging = charging
            if self.is_charging:
                self.bolt_animation.play_animation()
            else:
                self.bolt_animation.play_animation(is_reverse=True)

        if charging:
            if self.current_class != "charging":
                self.current_class = "charging"
                self.battery_icon.style_classes = [self.current_class]
                self.battery_percent.style_classes = [self.current_class]
        elif 30 < int(round(percent)) < 50:
            if self.current_class != "low":
                self.current_class = "low"
                self.battery_icon.style_classes = [self.current_class]
                self.battery_percent.style_classes = [self.current_class]

        elif int(round(percent)) <= 30:
            if self.current_class != "critical":
                self.current_class = "critical"
                self.battery_icon.style_classes = [self.current_class]
                self.battery_percent.style_classes = [self.current_class]
        elif self.current_class != "":
            self.current_class = ""
            self.battery_icon.style_classes = []
            self.battery_percent.style_classes = []

    def poll_batt(self):
        battery = psutil.sensors_battery()
        return battery if battery else None

    def on_click(self, *args):
        self.battery_percent_revealer.set_reveal_child(
            not self.battery_percent_revealer.get_child_revealed(),
        )
