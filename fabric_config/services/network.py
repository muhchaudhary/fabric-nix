import gi

from fabric.core.service import Property, Service, Signal
from fabric.utils import bulk_connect
from fabric import Application

gi.require_version("AstalNetwork", "0.1")
from gi.repository import AstalNetwork as Network


class FabricNetwork(Service):
    @Signal
    def changed(self) -> None: ...

    def __init__(self, **kwargs):
        self._network = Network.get_default()
        super().__init__(**kwargs)
        print(self._network.get_state())

        # self._network.connect("changed", )
        if self._network.get_primary() == Network.Primary.WIFI:
            print("Connected via WiFi")

        primary = self._network.get_primary()
        if primary == Network.Primary.WIFI:
            self._network.get_wifi().connect(
                "state-changed", self.on_wifi_state_changed
            )

    def on_wifi_state_changed(self, *_):
        print(_)


net = FabricNetwork()

app = Application(
    "fabric-network-demo",
)
app.run()
