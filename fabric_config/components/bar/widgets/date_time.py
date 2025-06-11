from gi.repository import GLib

from fabric.widgets.button import Button

import calendar
from datetime import date


class DayInMonthHighlightingCalendar(calendar.TextCalendar):
    def __init__(self, day_to_highlight):
        super().__init__()
        self._day_to_highlight = day_to_highlight

    def formatday(self, day: int, weekday: int, width: int) -> str:
        s = super().formatday(day, weekday, width)
        if day == self._day_to_highlight:
            s = f"<span foreground='red' background='black'>{s}</span>"
        return s


# class DateTime(Button):
#     def __init__(self, **kwargs):
#         super().__init__(name="panel-button", style="background-color: red", **kwargs)
#         self.interval = 1000
#         self.format = "%a %b %d  %I:%M %p"
#         self.update_label()
#         GLib.timeout_add(self.interval, self.update_label)

#         today = date.today()
#         year, month, day, *_ = today.timetuple()
#         self.set_tooltip_markup(
#             DayInMonthHighlightingCalendar(day_to_highlight=day).formatmonth(
#                 year, month, 3
#             )
#         )

#     def update_label(self, *args):
#         self.set_label(GLib.DateTime.new_now_local().format("%a %b %d  %I:%M %p"))
#         return True
