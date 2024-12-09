import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

class MainWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Menu")
        self.set_default_size(200, 100)

        self.menubar1=Gtk.MenuBar()
        self.menu1=Gtk.Menu()
        self.menuitem1=Gtk.MenuItem("File")
        self.menuitem1.set_submenu(self.menu1)
        self.menuitem2=Gtk.MenuItem("Open File")
        self.menuitem2.connect("activate", self.open_file)
        self.menuitem3=Gtk.MenuItem("Save File")
        self.menuitem3.connect("activate", self.save_file)
        self.menu1.append(self.menuitem2)
        self.menu1.append(self.menuitem3)
        self.menubar1.append(self.menuitem1)

        self.label1=Gtk.Label("Menu Test")
        self.label1.set_hexpand(True)
        self.label1.set_vexpand(True)

        self.grid=Gtk.Grid()
        self.grid.attach(self.menubar1, 0, 0, 1, 1)
        self.grid.attach(self.label1, 0, 1, 1, 1)
        self.add(self.grid)

    def open_file(self, menuitem2):
        print("Open File")

    def save_file(self, menuitem3):
        print("Save File")

win=MainWindow()
win.connect("delete-event", Gtk.main_quit)
win.show_all()
Gtk.main()