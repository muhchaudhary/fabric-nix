from utils.hadith_grabber import Hadith

from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.date_time import DateTime
from fabric.widgets.label import Label
from fabric.widgets.wayland import Window


class ClockWidget(Window):
    def __init__(self, **kwargs):
        self.center_box = CenterBox(name="clock-window")

        self.main_box = Box(
            name="clockbox",
            children=[
                DateTime(format_list=["%I:%M"], name="clock"),
                DateTime(format_list=["%A %B %d"], name="date", interval=10000),
            ],
            orientation="v",
        )

        self.center_box.add_center(self.main_box)

        super().__init__(
            layer="bottom",
            anchor="left top right",
            # margin="100px 0px 0px 0px",
            all_visible=True,
            exclusive=False,
            children=self.center_box,
        )

        self.show_all()


class HadithWidget(Window):
    def __init__(self, **kwargs):
        self.hadith_ref = Label(name="hadith-ref")
        self.hadith_ref.set_line_wrap(True)

        self.hadith_text = Label(name="hadith-text")
        self.hadith_text.set_line_wrap(True)

        self.hadith_book = Label(name="hadith-book")
        self.hadith_book.set_line_wrap(True)

        self.hadith_number = Label(name="hadith-number")
        self.hadith_number.set_line_wrap(True)

        self.hadith = Hadith()
        self.center_box = Box(
            name="hadith-box",
            orientation="v",
            children=[
                Box(children=self.hadith_ref),
                self.hadith_text,
                Box(children=[self.hadith_book, self.hadith_number]),
            ],
        )
        self.hadith.get_random_hadith()
        try:
            split_hadith = self.hadith.hadith_text.split(":", 1)
            self.hadith_ref.set_label(split_hadith[0])
            self.hadith_text.set_label(split_hadith[1])
        except:
            self.hadith_text.set_label(self.hadith.hadith_text)

        self.hadith_book.set_label(self.hadith.book_name)
        self.hadith_number.set_label(
            f"Book {self.hadith.book_number}, Hadith {self.hadith.hadith_number}, Arabic Number {self.hadith.arabic_number}"
        )
        super().__init__(
            layer="bottom",
            anchor="center",
            # margin="100px 0px 0px 0px",
            all_visible=True,
            exclusive=False,
            children=self.center_box,
        )
