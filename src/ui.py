import displayio
import vectorio

from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.label import Label


# FIXME:  Don't load fonts we don't use


class Fonts:
    def __init__(self):
        self._fonts = {}

    def load(self):
        # Pixel Operator (previously known as the 8-bit Operator) is a libre/free raster proportional and monospace sans serif typeface.
        # Source files are available at NotABug: https://notabug.org/HarvettFox96/ttf-pixeloperator
        # This typeface is made by Jayvee Enaguas (HarvettFox96), licensed under a Creative Commons Zero (CC0) 1.0. © 2009-2018.
        #
        # (Converted to BDF and then PCF by me)
        self._fonts["16px"] = bitmap_font.load_font("fonts/PixelOperator8-16.pcf")
        self._fonts["24px"] = bitmap_font.load_font("fonts/PixelOperator8-24.pcf")
        self._fonts["32px"] = bitmap_font.load_font("fonts/PixelOperator8-32.pcf")
        self._fonts["40px"] = bitmap_font.load_font("fonts/PixelOperator8-40.pcf")

        self._fonts["16px_bold"] = bitmap_font.load_font("fonts/PixelOperator8-Bold-16.pcf")
        self._fonts["24px_bold"] = bitmap_font.load_font("fonts/PixelOperator8-Bold-24.pcf")
        self._fonts["32px_bold"] = bitmap_font.load_font("fonts/PixelOperator8-Bold-32.pcf")
        self._fonts["40px_bold"] = bitmap_font.load_font("fonts/PixelOperator8-Bold-40.pcf")

    def get(self, style: str):
        if style in self._fonts:
            return self._fonts[style]
        return self._fonts["16px"]


class PageBase:
    def __init__(self, device, fonts: Fonts):
        self.device = device
        self.fonts = fonts
        self.group = displayio.Group()
        self._create()

    def _refresh(self):
        self.device.display.root_group = self.group
        self.device.display.refresh()

    def _create(self):
        pass

    def show(self, *args, **kwargs):
        pass


class PageStartup(PageBase):
    def _create(self):
        palette = displayio.Palette(2)
        palette[0] = 0x125690
        palette[1] = 0x569012

        top_rectangle    = vectorio.Rectangle(pixel_shader=palette, width=320, height=120, x=0, y=0, color_index=0)
        bottom_rectangle = vectorio.Rectangle(pixel_shader=palette, width=320, height=120, x=0, y=120, color_index=1)

        self.label_logging  = Label(self.fonts.get("32px_bold"), text="Logger", color=0xFFFFFF, x=60, y=55)
        self.label_transfer = Label(self.fonts.get("32px_bold"), text="Transfer", color=0xFFFFFF, x=30, y=180)

        self.group.append(top_rectangle)
        self.group.append(bottom_rectangle)
        self.group.append(self.label_logging)
        self.group.append(self.label_transfer)

    def show(self):
        self._refresh()


class PageError(PageBase):
    def _create(self):
        palette = displayio.Palette(1)
        palette[0] = 0x331111
        background = vectorio.Rectangle(pixel_shader=palette, width=320, height=240, x=0, y=0)

        self.label_title     = Label(self.fonts.get("32px_bold"), text="Error:", color=0xFF0000, x=20, y=40)
        self.label_message_1 = Label(self.fonts.get("16px_bold"), text="", color=0xFFFFFF, x=25, y=120)
        self.label_message_2 = Label(self.fonts.get("16px"), text="", color=0xFFFFFF, x=25, y=160)

        self.group.append(background)
        self.group.append(self.label_title)
        self.group.append(self.label_message_1)
        self.group.append(self.label_message_2)

    def show(self, message_1: str, message_2: str = ""):
        self.label_message_1.text = message_1
        self.label_message_2.text = message_2
        self._refresh()


class PageTransfer(PageBase):
    def _create(self):
        palette = displayio.Palette(1)
        palette[0] = 0x113311
        background = vectorio.Rectangle(pixel_shader=palette, width=320, height=240, x=0, y=0)

        self.label_title     = Label(self.fonts.get("32px_bold"), text="Transfer", color=0xFFFFFF, x=20, y=40)
        self.label_message_1 = Label(self.fonts.get("16px_bold"), text="", color=0xFFFFFF, x=20, y=120)
        self.label_message_2 = Label(self.fonts.get("16px"), text="", color=0xFFFFFF, x=20, y=160)
        self.label_message_3 = Label(self.fonts.get("16px"), text="", color=0xFFFFFF, x=20, y=200)

        self.group.append(background)
        self.group.append(self.label_title)
        self.group.append(self.label_message_1)
        self.group.append(self.label_message_2)
        self.group.append(self.label_message_3)

    def show(self, message_1: str = "", message_2: str = "", message_3: str = ""):
        self.label_message_1.text = message_1
        self.label_message_2.text = message_2
        self.label_message_3.text = message_3
        self._refresh()


class PageLogger(PageBase):
    def _create(self):
        palette = displayio.Palette(1)
        palette[0] = 0x111133
        background = vectorio.Rectangle(pixel_shader=palette, width=320, height=240, x=0, y=0)

        self.label_date_time         = Label(self.fonts.get("16px"), text="", color=0xFFFFFF, x=26, y=20)
        self.label_satellite_details = Label(self.fonts.get("16px"), text="", color=0xFFFFFF, x=26, y=50)
        self.label_fix_quality       = Label(self.fonts.get("16px_bold"), text="", color=0xFFFFFF, x=226, y=50)
        self.label_speed             = Label(self.fonts.get("40px_bold"), text="", color=0x00aa00, x=26, y=115)
        self.label_speed_suffix      = Label(self.fonts.get("16px_bold"), text="kmh", color=0x00aa00, x=226, y=125)
        self.label_stats             = Label(self.fonts.get("16px"), text="", color=0xFFFFFF, x=26, y=180)
        self.label_battery_status    = Label(self.fonts.get("16px"), text="", color=0xFFFFFF, x=26, y=210)

        self.group.append(background)
        self.group.append(self.label_date_time)
        self.group.append(self.label_satellite_details)
        self.group.append(self.label_fix_quality)
        self.group.append(self.label_speed)
        self.group.append(self.label_speed_suffix)
        self.group.append(self.label_stats)
        self.group.append(self.label_battery_status)

    def show(self, date_time: str, satellite_details: str, fix_quality: str, speed: str, stats: str, battery_status: str):
        self.label_date_time.text         = date_time
        self.label_satellite_details.text = satellite_details
        self.label_fix_quality.text       = fix_quality
        self.label_speed.text             = speed
        self.label_stats.text             = stats
        self.label_battery_status.text    = battery_status

        self._refresh()

