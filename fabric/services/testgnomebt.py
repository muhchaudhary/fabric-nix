import fabric
import time
from fabric.services.bluetooth import BluetoothDevice,BluetoothClient
from fabric.utils import invoke_repeater

btclient = BluetoothClient()
devices = []

def check_connection(a):
    print("DEVICE IS CONNECTED:", a)

def new_device(x,y):
    if y == "94:DB:56:D0:DA:72":
        new_device = BluetoothDevice(
            btclient.props.devices[y],
            btclient
        )
        devices.append(new_device)
        new_device.connect("notify::connected", lambda _, __: check_connection(new_device.connected))
        new_device.set_connection(True)
        time.sleep(10)
        new_device.set_connection(False)

def remove_device(x,y):
    print(x,y)

btclient.connect("device-added",new_device)
btclient.connect("device-removed", remove_device)


if __name__ == "__main__":

    fabric.start()