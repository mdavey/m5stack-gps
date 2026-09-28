# m5stack-gps
# Copyright (c) 2026 Matthew Davey
# SPDX-License-Identifier: MIT

import os
import time
import traceback
import binascii
import json

import board
import busio
import displayio
import supervisor
import fourwire
import sdcardio
import storage
import busdisplay
import wifi
import socketpool
import gc

from axp2101 import AXP2101, BatteryStatus
from adafruit_httpserver import Request, Response, Server, Route, ChunkedResponse, INTERNAL_SERVER_ERROR_500
import adafruit_focaltouch

import config
from ui import PageStartup, Fonts, PageError, PageTransfer, PageLogger
from gps import GPSState, GPSStateException


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


def write_buffered_lines_to_file(filename, lines):
    with device.sd_card():
        with open(filename, "a") as f:
            for line in lines:
                f.write(line + "\n")
            f.flush()
            os.sync()


################################################################

device = CoreS3()
device.display.auto_refresh = False

i2c = board.I2C()
pmic = AXP2101(i2c)

def get_battery_str():
    if pmic.is_battery_connected:
        state = 'Unknown'
        if pmic.battery_status is BatteryStatus.STANDBY:
            state = 'Battery'
        elif pmic.battery_status is BatteryStatus.CHARGING:
            state = 'Charging'
        elif pmic.battery_status is BatteryStatus.DISCHARGING:
            state = 'Discharging'

        return "{}: {:.2f}v".format(state, pmic.battery_voltage/1000)
    else:
        return "No battery connected"

touch = adafruit_focaltouch.Adafruit_FocalTouch(i2c, debug=False)

fonts = Fonts()
fonts.load()

page_startup = PageStartup(device, fonts)
page_error = PageError(device, fonts)
page_transfer = PageTransfer(device, fonts)
page_logger = PageLogger(device, fonts)


################################################################


def wait_for_gps_present(uart: busio.UART):
    # Send initial commands, and check that data comes back
    start_time = time.monotonic()

    while True:

        # noinspection PyTypeChecker
        uart.write("version\r\n")
        time.sleep(0.1)

        if time.monotonic() - start_time > 1:
            page_error.show("No GPS Found", "For: {}s".format(int(time.monotonic() - start_time)))

        if uart.in_waiting == 0:
            continue

        # Read some stuff, and ignore it
        data = uart.readline()
        if not data:
            continue

        # We got something, all goto to continue
        break


################################################################


def startup_ui():
    start_time = time.monotonic()
    page_startup.show()

    while True:

        # If we've been on this screen for a while, just to the main_ui()
        if (config.AUTO_LOG_TIMEOUT  > 0) and (time.monotonic() - start_time > config.AUTO_LOG_TIMEOUT):
            main_ui()

        # Check if a button has been pressed
        try:
            if touch.touched:
                if len(touch.touches) != 1:  # No Multitouch
                    continue

                # CANNOT assume that there's still a touch even at this point
                # Iterate, because and grab it
                for touch_event in touch.touches:
                    if touch_event["y"] > 120:  # Top!
                        main_ui()
                    else:
                        transfer_ui()

        # RuntimeError: buffer size must match format  (I2C data was wrong in unpack() call!?)
        except RuntimeError as e:
            traceback.print_exception(e)
            continue


################################################################


def transfer_default_route(request: Request):
    with device.sd_card():
        # Just check for file ending in ".csv"  we don't have os.path so if someone makes a directory "foo.csv/" sucks to be them
        all_files = [filename for filename in os.listdir("/sd/")]

    html = "<!DOCTYPE html>"
    html += "<html><body>"
    html += "<h1>Files:</h1>"
    html += "<ul>"
    for filename in all_files:
        html += "<li><a href=\"/get/{}\">{}</a></li>".format(filename, filename)
    html += "</ul>"
    html += "<pre>{}</pre>".format(request)
    html += "</body></html>"

    return Response(request, body=html, content_type="text/html")


def transfer_api_file_exists(filename: str) -> bool:
    try:
        os.stat(filename)
        return True
    except OSError:
        return False


def transfer_api_get_file_content(request: Request, filename):
    def chunked_data():
        with device.sd_card():
            with open("/sd/{}".format(filename), "rb") as f:
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    yield chunk

    try:
        return ChunkedResponse(request, chunked_data, content_type="text/csv")
    except Exception as e:
        traceback.print_exception(e)
        return Response(request, status=INTERNAL_SERVER_ERROR_500, body=str(e), content_type="text/plain")


def transfer_api_get_file_list(request: Request):
    try:
        file_details = []
        with device.sd_card():
            for filename in os.listdir("/sd/"):
                file_info = os.stat("/sd/{}".format(filename))
                file_details.append({
                    'filename': filename,
                    'size': file_info[6]  # tuple has no attribute .st_size
                })

        body = json.dumps(file_details)

        return Response(request, body=body, content_type="application/json")
    except Exception as e:
        traceback.print_exception(e)
        return Response(request, status=INTERNAL_SERVER_ERROR_500, body=str(e), content_type="text/plain")


def transfer_api_get_crc32(request: Request, filename: str):
    try:
        crc32_value = 0
        with device.sd_card():
            with open("/sd/{}".format(filename), "rb") as f:
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    crc32_value = binascii.crc32(chunk, crc32_value)

            body = hex(crc32_value) # If I move this out of the device.sd_card block CircuitPython hard crashes...
            return Response(request, body=body, content_type="text/plain")

    except Exception as e:
        traceback.print_exception(e)
        return Response(request, status=INTERNAL_SERVER_ERROR_500, body=str(e), content_type="text/plain")


def transfer_api_delete_file(request: Request, filename: str):
    try:
        with device.sd_card():
            os.unlink(("/sd/{}".format(filename)))

            body = "{} removed".format(filename)
            return Response(request, body=body, content_type="text/plain")

    except Exception as e:
        traceback.print_exception(e)
        return Response(request, status=INTERNAL_SERVER_ERROR_500, body=str(e), content_type="text/plain")


def transfer_api_soft_reset(request: Request):
    supervisor.reload()

    body = "performing soft reset"
    return Response(request, body=body, content_type="text/plain")


def transfer_ui():
    page_transfer.show("Connecting...", config.WIFI_SSID, "")
    wifi.radio.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    while not wifi.radio.connected:
        time.sleep(0.1)

    page_transfer.show("Connected", config.WIFI_SSID, "http://{}:5000/".format(wifi.radio.ipv4_address))

    time.sleep(1)

    pool = socketpool.SocketPool(wifi.radio)
    server = Server(pool, debug=True)

    server.add_routes([
        Route("/", "GET", transfer_default_route),
        Route("/get/<filename>", "GET", transfer_api_get_file_content),
        Route("/list", "GET", transfer_api_get_file_list),
        Route("/crc32/<filename>", "GET", transfer_api_get_crc32),
        Route("/delete/<filename>", "DELETE", transfer_api_delete_file),
        Route("/reset", "GET", transfer_api_soft_reset),
    ])

    server.serve_forever(host=str(wifi.radio.ipv4_address), port=5000)


################################################################


def main_ui():

    print("Free RAM:", gc.mem_free(), "bytes")

    # PortaA
    board.PORTA_I2C().deinit()
    uart = busio.UART(
        tx=board.PORTA_SCL,   # who even knows what the wiring should look like here
        rx=board.PORTA_SDA,
        baudrate=115200,
        timeout=0.01, # 10ms wait for a character
        receiver_buffer_size=16384,  # I **think** when switching to 5Hz, when we re-init the display we overflow
    )

    # PortB
    # uart = busio.UART(
    #     tx=board.PORTB_IN,   # I might have wired this up wrong :-)
    #     rx=board.PORTB_OUT,
    #     baudrate=115200,
    #     timeout=0.01, # 10ms wait for a character
    # )

    # Spin for a while waiting for any data to come back from the UART before continuing
    wait_for_gps_present(uart)


    # Send the init commands.  At least try to read the responses.
    for command in config.GPS_INIT_COMMANDS:
        uart.write(command + "\r\n")
        print("SEND: {}".format(command))
        response = uart.readline()
        if response is not None:
            print("RECV: {}".format(response.decode("utf-8").strip()))


    # Start logging points!
    current_filename = None
    lines_waiting_to_write = []
    stats_uart_lines_recv = 0
    stats_lines_written = 0
    gps_state = GPSState()
    last_uart_data = time.monotonic()  # Technically this is true  wait_for_gps_present()  just returned!

    while True:

        if time.monotonic() - last_uart_data > 3:
            page_error.show("No GPS data", "For {}s".format(int(time.monotonic() - last_uart_data)))
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
        try:
            should_update_ui = gps_state.update(data)
        except GPSStateException as e:
            traceback.print_exception(e)
            page_error.show("Error with GPS State", str(e))
            time.sleep(5)
            supervisor.reload()

        # Supervisor.reload() above reloads everything, will never get here with invalid should_update_ui var
        # noinspection PyUnboundLocalVariable
        if should_update_ui and not gps_state.has_fix:
            page_error.show("No GPS Lock", "(UART Data: {})".format(stats_uart_lines_recv))

        if should_update_ui and gps_state.has_fix:
            # print("{} -- Fix Quality: {}".format(gps_state.current_log_line, gps_state.fix_quality))
            lines_waiting_to_write.append(gps_state.current_log_line)

            if len(lines_waiting_to_write) >= config.LINES_TO_BUFFER:

                if current_filename is None:
                    current_filename = "/sd/{}.csv".format(gps_state.current_utc.replace("-", "").replace(":", "").replace("T", "_"))
                    lines_waiting_to_write.insert(0, "timestamp,latitude,longitude,altitude,speed,num_satellites,hdop")

                write_buffered_lines_to_file(current_filename, lines_waiting_to_write)
                stats_lines_written += len(lines_waiting_to_write)
                lines_waiting_to_write = []

            # If we have a SBAS fix, put it on the UI
            fix_quality_str = ""
            if gps_state.fix_quality == 2:
                fix_quality_str = "SBAS"

            page_logger.show(
                gps_state.current_utc,
                "Satellites: {}".format(gps_state.current_sat_count),
                fix_quality_str,
                "{:5.1f}".format(gps_state.current_speed),
                "Points saved: {}".format(stats_lines_written),
                get_battery_str())
                # "{} bytes free".format(gc.mem_free()))


################################################################


startup_ui()
