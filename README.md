# GPS Logger (M5Stack CoreS3)

A GPS data logger built on the **M5Stack CoreS3** (ESP32-S3) running **CircuitPython**.
It reads NMEA sentences from a **Unicore UM980** GNSS receiver over UART, renders a
live dashboard on the built-in 3.2" TFT display, monitors the battery via the
AXP2101 PMIC, and logs every fix to an SD card as CSV.

**Not yet ready for use**

## Screenshots

| Startup Screen                          | Main Logging Screen      |
|-----------------------------------------|--------------------------|
| ![](screenshots/screenshot_startup.jpg) | ![](screenshots/screenshot_main.jpg) |  

*(Yes it's upside down, I drilled holes before checking where the cable had to reach)*


## Features

- Basic Display with time and speed and battery life (if battery turned on)
- Works around M5Stack CoreS3 using the same pin for LCD D/C **and** MISO for SD Card.
- Exposes an HTTP server for getting CSV files off SD Card
- CLI script to download all the files locally and convert to GPX


## Hardware

| Component     | Details                                                                    |
|---------------|----------------------------------------------------------------------------|
| MCU board     | M5Stack CoreS3 (ESP32-S3)                                                  |
| GNSS receiver | Unicore UM980. Port A/B Grove (TX/RX wiring may be swapped!) @ 115200 baud |
| Storage       | MicroSD card                                                               |
| Firmware      | Adafruit CircuitPython 10.x  (Nightly with SPI fix)                        |


## Project layout

```
  .
  ├── deploy.sh                          # Shell script to copy code to M5Stack device
  ├── sync_data.py                       # Python script to download CSV files from web API and convert into GPX
  ├── sync_data.last_ip                  # Cache file holding the last used IP address
  ├── data/                              # sync_data.py will place CSV and GPX files here 
  └── src/ 
      ├── code.py                        # Main M5Stack program
      ├── config.py                      # Holds SSID/Password and other settings (gitignored, copy from config.py.sample)
      ├── config.py.sample               # Template for config.py
      ├── gps.py                         # Parses multiple messages and presents a "GPSState"
      ├── nmea.py                        # Parses raw nmea messages into typed objects
      ├── nano_degrees.py                # Integer-math lat/long type (decimal degrees at nano-degree precision)
      ├── lib/
      │   ├── axp2101.py                 # AXP2101 PMIC driver (Adafruit)
      │   ├── adafruit_focaltouch.mpy    # FT6336U touch driver (Adafruit)
      │   ├── adafruit_bitmap_font/      # Bitmap font loader (Adafruit)
      │   ├── adafruit_httpserver/       # HTTP Webserver
      │   └── font_free_sans_*/          # FreeSans PCF bitmap fonts
      └── sd/
          └── placeholder.txt            # Make sure SD mount point is present
```


## GPS configuration

The receiver is configured at every boot via UART commands:

```
unlogall                     # disable all nmea messages
config signalgroup 2         # switch to signal group 2  (GNSS frequency preset)
mode rover                   # rover  (not a base station)
config sbas enable span      # enable SBAS for SouthPAN  (Australia)
gngga 1                      # log GGA messages  (fix details)
gnrmc 1                      # log RMC message   (speed time & date)
version
```

**Note:** If all messages are enabled, there seems to be an issue with the 
UART keeping up.


## Log format

Logged to `/sd/[yyyymmdd]_[hhmmss]Z.csv`

```
timestamp,latitude,longitude,altitude,speed,num_satellites,hdop
2026-08-15T14:30:00Z,-47.276949070,142.138929220,12.34,42.65,12,0.9
```

- `timestamp` — UTC, `YYYY-MM-DDTHH:MM:SSZ`
- `latitude`/`longitude` — decimal degrees
- `altitude` — metres (GGA)
- `speed` — km/h (RMC overground speed, knots × 1.852)
- `num_satellites` — satellite count (GGA)
- `hdop` — horizontal dilution of precision (GGA)

A fix is accepted when `hdop < 100` and `sats > 3`.

**Note:** We're not natively using a GPX because it's pretty space inefficient 
and not easy to append too.


## Getting Data Off

1. Remove the SD Card and copy the CSV files.

2. On startup, enter file transfer mode.  Device will connect to the Wifi AP 
defined in `src/config.py`.  You can browse and download files via a web
browser: `http://ip:5000/`

3. Rather than using a web browser to manually download the files, enter 
mode and then use `sync_data.py` to download any logs to `./data/` and convert
them to GPX.


## Issues

Accessing the SD Card *and* the Display at the same time doesn't seem to be
possible as the CoreS3 re-used the SPI MISO pin for the DC pin of the LCD.

This probably isn't a big deal if you were writing the code in C, but it
required a workaround for CircuitPython.  The workaround seems okay, but it 
does make the screen redraw when switching between the two devices.

For a logger, I'm prepared to live with this.

Related to this issue, if you are having trouble running CircuitPython 10.x, 
make sure to use firmware that includes PR11155.  e.g. 
`adafruit-circuitpython-m5stack_cores3-en_US-20260731-main-PR11155-719f88d.bin`   


## References

- [UM980 configuration commands](https://www.ardusimple.com/how-to-configure-unicore-um980-um981-um982/#Frequently-used-commands)
- [NMEA-0183 GGA message](https://receiverhelp.trimble.com/alloy-gnss/en-us/NMEA-0183messages_GGA.html)
- Fonts from https://github.com/adafruit/circuitpython-fonts
- PRN 122 or 139 are SouthPAN SBAS

## AI Disclaimer

* Circuit Python code (and bugs) created by a human.
* `sync_data.py` created by GLM 5.2


## License

MIT
