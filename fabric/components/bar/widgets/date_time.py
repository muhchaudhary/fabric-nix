from gi.repository import GLib

from fabric.widgets.button import Button


class DateTime(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)
        self.interval = 1000
        self.format = "%a %b %d  %I:%M %p"
        self.update_label()
        GLib.timeout_add(self.interval, self.update_label)

    def update_label(self, *args):
        self.set_label(GLib.DateTime.new_now_local().format("%a %b %d  %I:%M %p"))
        return True
