# Run this script from inside src directory with `uv run local_ui_test.py`


import sys
sys.path.append('lib')

import pygame
import time
from blinka_displayio_pygamedisplay import PyGameDisplay
from ui import PageStartup, Fonts, PageError, PageTransfer, PageLogger


def screenshot(display, path):
    display._refresh_display()  # make sure the window holds the current frame
    pygame.image.save(display._pygame_screen, path)


################################################


class FakeDevice:
    def __init__(self, display):
        self.display = display


display = PyGameDisplay(width=320, height=240)
device = FakeDevice(display)

fonts = Fonts()
fonts.load()


page_startup = PageStartup(device, fonts)
page_startup.show()
screenshot(display, "../screenshots/page_startup.png")

time.sleep(1)

page_error = PageError(device, fonts)
page_error.show("No GPS data", "For {}s".format(4))
screenshot(display, "../screenshots/page_error.png")

time.sleep(1)

page_transfer = PageTransfer(device, fonts)
page_transfer.show("Connected", "this is my wifi ssid", "http://{}:5000".format("127.0.0.1"))
screenshot(display, "../screenshots/page_transfer.png")

time.sleep(1)

page_logger = PageLogger(device, fonts)
page_logger.show(
    "2024-09-01T12:22:34Z",
    "Satellites: 21",
    "CBAS",
    "{:5.1f}".format(41.1238),
    "Points saved: {}".format(631),
    "No battery connected")
screenshot(display, "../screenshots/page_logger.png")

time.sleep(1)


while True:
    if display.check_quit():
        break