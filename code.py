import os
import time
import traceback
from collections import namedtuple

import board
import busio
import displayio
import vectorio
import fourwire
import sdcardio
import storage
import busdisplay
import supervisor

from axp2101 import AXP2101  # battery chip


from adafruit_display_text.label import Label
import adafruit_focaltouch


import font_free_sans_24
import font_free_sans_48

FONT_SMALL = font_free_sans_24.FONT
FONT_LARGE = font_free_sans_48.FONT

# How many GPS coords to buffer before writing to the SD Card  (1hz)
LINES_TO_BUFFER = 10


################################################################


# Technically if you added a "saveconfig" you'd only have to do this once
# But nice to make sure it's in a mode I want
GPS_INIT_COMMANDS = [
    "mode rover",
    "gngga 1",
    "gnrmc 1",
    "gngga com2 1",
    "gnrmc com2 1",
    "version"
]


################################################################


class CoreS3:
    def __init__(self):
        self.spi = None
        self.display = None
        self.create_display()

    def sd_card(self):
        # Return a context manager bound to this specific instance
        return SDCardContext(self)

    def create_display(self):
        displayio.release_displays()

        self.spi = busio.SPI(clock=board.TFT_SCK, MOSI=board.TFT_MOSI)

        four_wire_display_bus = fourwire.FourWire(
            self.spi,
            command=board.TFT_DC,
            chip_select=board.TFT_CS,
            baudrate=40000000
        )

        # This comes from the C code for the M5Stack CoreS3
        # init_seq = (b"\x01\x80\x80"              # Software reset then delay 0x80 (128ms)
        #             b"\xC8\x03\xFF\x93\x42"      # Turn on the external command
        #             b"\xC0\x02\x12\x12"          # Power Control 1
        #             b"\xC1\x01\x03"              # Power Control 2
        #             b"\xC5\x01\xF2"              # VCOM Control 1
        #             b"\xB0\x01\xE0"              # RGB Interface SYNC Mode
        #             b"\xF6\x03\x01\x00\x00"      # Interface control
        #             b"\xE0\x0F\x00\x0C\x11\x04\x11\x08\x37\x89\x4C\x06\x0C\x0A\x2E\x34\x0F"   # Positive Gamma Correction
        #             b"\xE1\x0F\x00\x0B\x11\x05\x13\x09\x33\x67\x48\x07\x0E\x0B\x2E\x33\x0F"   # Negative Gamma Correction
        #             b"\xB6\x04\x08\x82\x1D\x04"  # Display Function Control
        #             b"\x3A\x01\x55"              # COLMOD: Pixel Format Set 16 bit
        #             b"\x21\x00"                  # Display inversion ON
        #             b"\x36\x01\x08"              # Memory Access Control: RGB order
        #             b"\x11\x80\x78"              # Exit Sleep then delay 0x78 (120ms)
        #             b"\x29\x80\x78")             # Display on then delay 0x78 (120ms)

        # It appears that it's not really needed if it's been set up once (even after displayio.release_displays())
        # TODO: Check if there is a 'warm_init' that's better?
        init_seq = b""

        self.display = busdisplay.BusDisplay(
            four_wire_display_bus,
            init_seq,
            width=320,
            height=240,
            colstart=0,
            rowstart=0,
            rotation=0,
            color_depth=16,
            grayscale=False,
            pixels_in_byte_share_row=False,
            bytes_per_cell=1,
            reverse_pixels_in_byte=False,
            # reverse_bytes_in_word=True,  Doesn't exist in Python code
            set_column_command=0x2a,
            set_row_command=0x2b,
            write_ram_command=0x2c,
            backlight_pin=None,
            brightness_command=0x100, # NO_BRIGHTNESS_COMMAND
            brightness=1.0,
            single_byte_bounds=False,
            data_as_commands=False,
            auto_refresh=False,  # <-- Turn off auto-refresh by default
            native_frames_per_second=61,
            backlight_on_high=True,
            SH1107_addressing=False,
            # backlight_pwm_frequency=50000 Doesn't exist in Python code
            )

        self.display.rotation = 180

        # self.display.root_group = displayio.CIRCUITPYTHON_TERMINAL
        self.display.refresh()


class SDCardContext:
    def __init__(self, core_s3: CoreS3):
        self.core: CoreS3 = core_s3

    def __enter__(self):
        displayio.release_displays()
        self.core.spi.deinit()
        self.sd_spi = busio.SPI(clock=board.TFT_SCK, MOSI=board.TFT_MOSI, MISO=board.TFT_DC)
        self.sdcard = sdcardio.SDCard(self.sd_spi, board.SDCARD_CS)
        self.vfs = storage.VfsFat(self.sdcard)
        storage.mount(self.vfs, "/sd")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        storage.umount(self.vfs)
        self.sdcard.deinit()
        self.sd_spi.deinit()
        self.core.create_display()
        return False


################################################################


GGA = namedtuple('GGA', ['utc_time', 'latitude', 'longitude', 'fix_quality', 'satellites', 'hdop', 'altitude'])
RMC = namedtuple('RMC', ['utc_time', 'utc_date', 'status', 'latitude', 'longitude', 'speed_kmh', 'track'])

UtcTime = namedtuple('UtcTime', ['hour', 'min', 'sec'])
UtcDate = namedtuple('UtcDate', ['year', 'month', 'day'])


def parse_degrees(nmea_geo: str, direction: str):
    """Convert NMEA coordinate strings into standard float decimal degrees."""
    if not nmea_geo or not direction: return 0.0
    try:
        raw = float(nmea_geo)
        degrees = int(raw / 100)
        minutes = raw - (degrees * 100)
        decimal = degrees + (minutes / 60.0)
        if direction in ('S', 'W'): decimal = -decimal
        return decimal
    except ValueError: return 0.0


def safe_float(val: str):
    """Safely convert empty or invalid strings to floats without throwing errors."""
    try: return float(val) if val else 0.0
    except ValueError: return 0.0


def safe_int(val: str):
    """Safely convert empty or invalid strings to integers."""
    try: return int(val) if val else 0
    except ValueError: return 0


def parse_utc_time(val: str):
    # hhmmss.ss
    return UtcTime(
        hour=safe_int(val[0:2]),
        min=safe_int(val[2:4]),
        sec=safe_int(val[4:6])
    )


def parse_utc_date(val: str):
    # ddmmyy
    return UtcDate(
        year=2000 + safe_int(val[4:6]),
        month=safe_int(val[2:4]),
        day=safe_int(val[0:2])
    )


def parse_gga(parts: list):
    # $--GGA,hhmmss.ss,llll.ll,a,yyyyy.yy,a,x,xx,x.x,x.x,M,x.x,M,x.x,xxxx*hh
    return GGA(
        utc_time=parse_utc_time(parts[1]),
        latitude=parse_degrees(parts[2], parts[3]),
        longitude=parse_degrees(parts[4], parts[5]),
        fix_quality=safe_int(parts[6]),
        satellites=safe_int(parts[7]),
        hdop=safe_float(parts[8]),
        altitude=safe_float(parts[9])
    )


def parse_rmc(parts: list):
    # $--RMC,hhmmss.ss,A,llll.ll,a,yyyyy.yy,a,x.x,x.x,ddmmyy,x.x,a,a*hh
    return RMC(
        utc_time=parse_utc_time(parts[1]),
        utc_date=parse_utc_date(parts[9]),
        status=parts[2],
        latitude=parse_degrees(parts[3], parts[4]),
        longitude=parse_degrees(parts[5], parts[6]),
        speed_kmh=safe_float(parts[7])*1.852,
        track=safe_float(parts[8])
    )


def parse_nmea(raw_sentence: str):
    """Clean the raw string, identify its type, and route to the correct parser."""
    if not raw_sentence.startswith('$'): return None

    # Strip any trailing carriage returns, newlines, and the checksum split
    clean_line = raw_sentence.strip().split('*')[0]
    parts = clean_line.split(',')

    # Extract sentence identifier (e.g., GPGGA, GNRMC -> GGA, RMC)
    msg_type = parts[0][3:] if len(parts[0]) > 3 else ""

    if msg_type == "GGA": return parse_gga(parts)
    elif msg_type == "RMC": return parse_rmc(parts)

    return None


################################################################


class GPSState:
    """Holds the current GPS state (because there are multiple messages each second that need to be combined)"""
    def __init__(self):
        self.last_gga = None
        self.last_rmc = None

        self.has_fix = False

        self.current_utc = None
        self.current_log_line = None
        self.current_sat_count = None
        self.current_speed = None


    def update(self, nmea_raw_data):
        """Pass a raw nmea data.  Returns True once each second (a GGA and RMC message)"""

        # Try to parse it
        try:
            text = nmea_raw_data.decode("utf-8").strip()
            msg = parse_nmea(text)
        except Exception as e:
            print("Error looked like NMEA message but wasn't: ", nmea_raw_data, e)
            traceback.print_exception(e)
            return False

        # Couldn't?
        if msg is None:
            print("Raw: ", text)
            return False


        if type(msg) is GGA:
            if self.last_gga is not None:
                print("ERROR:  Two GGA without a RMC")
                # supervisor.reload()
            else:
                self.last_gga = msg

        if type(msg) is RMC:
            if self.last_rmc is not None:
                print("ERROR:  Two RMC without a GGA")
                # supervisor.reload()
            else:
                self.last_rmc = msg

        if self.last_gga and self.last_rmc:
            if str(self.last_gga.utc_time) != str(self.last_rmc.utc_time):
                print("ERROR:  GGA and RMC out of sync!?")
                supervisor.reload()

            # 2011-12-31T23:59:59Z
            line_utc = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
                self.last_rmc.utc_date.year,
                self.last_rmc.utc_date.month,
                self.last_rmc.utc_date.day,
                self.last_rmc.utc_time.hour,
                self.last_rmc.utc_time.min,
                self.last_rmc.utc_time.sec
            )

            # time,lat,long,altitude,speed,sats,hdop,voltage
            line = "{},{:.5f},{:.5f},{:.2f},{:.2f},{},{}".format(
                line_utc,
                self.last_gga.latitude,
                self.last_gga.longitude,
                self.last_gga.altitude,
                self.last_rmc.speed_kmh,
                self.last_gga.satellites,
                self.last_gga.hdop
            )

            if self.last_gga.hdop < 100 and self.last_gga.satellites > 3:
                self.has_fix = True
                self.current_utc = line_utc
                self.current_log_line = line
                self.current_sat_count = self.last_gga.satellites
                self.current_speed = self.last_rmc.speed_kmh
            else:
                self.has_fix = False

            self.last_gga = None
            self.last_rmc = None

            # Update the UI
            return True

        # Don't update the UI
        return False


################################################################


def write_buffered_lines_to_file(filename, lines):
    with device.sd_card():
        with open(filename, "a+") as f:
            for line in lines:
                f.write(line + "\n")
            f.flush()
            os.sync()


################################################################


i2c = board.I2C()
pmic = AXP2101(i2c)

def get_battery_str():
    if pmic.is_battery_connected:
        return "Battery voltage {:.2f}v".format(pmic.battery_voltage/1000)
    else:
        return "No battery connected"


################################################################


touch = adafruit_focaltouch.Adafruit_FocalTouch(i2c, debug=False)


################################################################

device = CoreS3()
device.display.auto_refresh = False  # Manual refresh for smoother updates

# Startup page, chose between modes
page_startup = displayio.Group()

startup_label    = Label(FONT_LARGE, text="Start Logging", color=0xFFFFFF, x=20, y=55)
startup_messages = Label(FONT_LARGE, text="Transfer Files", color=0xFFFFFF, x=15, y=175)

startup_palette = displayio.Palette(2)
startup_palette[0] = 0x125690
startup_palette[1] = 0x569012

top_rectangle = vectorio.Rectangle(pixel_shader=startup_palette, width=320, height=120, x=0, y=0, color_index=0)
bottom_rectangle = vectorio.Rectangle(pixel_shader=startup_palette, width=320, height=120, x=0, y=120, color_index=1)

page_startup.append(top_rectangle)
page_startup.append(bottom_rectangle)
page_startup.append(startup_label)
page_startup.append(startup_messages)


# Main GPS Logging page
page_main = displayio.Group()

date_time_label = Label(FONT_SMALL, text="", color=0xFFFFFF, x=20, y=20)
sats_label      = Label(FONT_SMALL, text="", color=0xFFFFFF, x=20, y=50)
speed_label     = Label(FONT_LARGE, text="", color=0xFF0000, x=40, y=110)
stats_label     = Label(FONT_SMALL, text="", color=0xFFFFFF, x=20, y=180)
battery_label   = Label(FONT_SMALL, text="", color=0xFFFFFF, x=20, y=210)

for label in [date_time_label, sats_label, speed_label, stats_label, battery_label]:
    page_main.append(label)


# Error page.  Display an error
page_error = displayio.Group()

error_title_label = Label(FONT_LARGE, text="Error:", color=0xFF0000, x=20, y=60)
error_label = Label(FONT_SMALL, text="", color=0xFFFFFF, x=20, y=120)

page_error.append(error_title_label)
page_error.append(error_label)


def update_main_ui(datetime, sats, speed, stats_lines_written):

    device.display.root_group = page_main

    date_time_label.text = datetime
    sats_label.text      = "Sat count: {}".format(sats)
    speed_label.text     = "{:3.1f} kmh".format(speed)
    speed_label.color    = 0x00FF00

    battery_label.text   = get_battery_str()
    stats_label.text     = "Points logged: {}".format(stats_lines_written)

    device.display.refresh()


def update_error_ui(message: str):
    device.display.root_group = page_error
    error_label.text = message
    device.display.refresh()


def update_startup_ui():
    device.display.root_group = page_startup
    device.display.refresh()


################################################################


def wait_for_gps_present(uart: busio.UART):
    # Send initial commands, and check that data comes back
    start_time = time.monotonic()

    print("Checking for GPS")

    while True:

        uart.write("version\r\n")
        time.sleep(0.1)

        if time.monotonic() - start_time > 1:
            update_error_ui("No GPS Found for: {}s".format(int(time.monotonic() - start_time)))

        if uart.in_waiting == 0:
            continue

        # Read some stuff, and ignore it
        data = uart.readline()
        if not data:
            continue

        # We got something, all goto to continue
        break


################################################################

def startup():

    update_startup_ui()

    while True:
        if touch.touched:
            if len(touch.touches) != 1:  # No Multitouch
                continue

            # CANNOT assume that there's still a touch even at this point
            # Iterate, because and grab it
            for touch_event in touch.touches:
                if touch_event["y"] > 120:  # Top!
                    main()
                else:
                    update_error_ui("Bottom")
                    time.sleep(1)
                    update_startup_ui()


def main():

    # PortaA
    board.PORTA_I2C().deinit()
    uart = busio.UART(
        tx=board.PORTA_SCL,   # who even knows what the wiring should look like here
        rx=board.PORTA_SDA,
        baudrate=115200,
        timeout=0.01, # 10ms wait for a character
    )


    # PortB
    # uart = busio.UART(
    #     tx=board.PORTB_IN,   # I might have wired this up wrong :-)
    #     rx=board.PORTB_OUT,
    #     baudrate=115200,
    #     timeout=0.01, # 10ms wait for a character
    # )

    # Spin for a while waiting for a message to come back from the GPS before continuing
    wait_for_gps_present(uart)

    # Main loop starts here
    print("Starting:")

    current_filename = None
    lines_waiting_to_write = []
    stats_uart_lines_recv = 0
    stats_lines_written = 0
    gps_state = GPSState()
    last_uart_data = time.monotonic()  # Technically this is true  wait_for_gps_present()  just returned!


    while True:

        if time.monotonic() - last_uart_data > 3:
            update_error_ui("No GPS data: {}s".format(int(time.monotonic() - last_uart_data)))
            time.sleep(0.5)

        # Check num bytes in buffer
        if uart.in_waiting == 0:
            continue

        # Try to read entire line  (this is iffy on ESP32 with printing to USB/UART and all messages enabled on @ 115200)
        data = uart.readline()
        if not data:
            continue

        stats_uart_lines_recv += 1
        last_uart_data = time.monotonic()

        # Update our state, and check if we have a fix
        should_update_ui = gps_state.update(data)

        if should_update_ui and not gps_state.has_fix:
            update_error_ui("No Lock: ({})".format(stats_uart_lines_recv))

        if should_update_ui and gps_state.has_fix:
            print(gps_state.current_log_line)
            lines_waiting_to_write.append(gps_state.current_log_line)

            if len(lines_waiting_to_write) >= LINES_TO_BUFFER:

                if current_filename is None:
                    current_filename = "/sd/{}.csv".format(gps_state.current_utc.replace("-", "").replace(":", "").replace("T", "_"))

                write_buffered_lines_to_file(current_filename, lines_waiting_to_write)
                stats_lines_written += len(lines_waiting_to_write)
                lines_waiting_to_write = []

            update_main_ui(gps_state.current_utc, gps_state.current_sat_count, gps_state.current_speed, stats_lines_written)


# main()
startup()
