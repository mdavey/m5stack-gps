import traceback
from nmea import GGA, RMC, DTM, parse_nmea


try:
    # This block executes on your PC during type checking,
    # but fails gracefully and safely on the microcontroller.
    from typing import Optional
except ImportError:
    pass


class GPSStateException(Exception):
    pass


class GPSState:
    """Holds the current GPS state (because there are multiple messages each second that need to be combined)"""
    def __init__(self):
        self._last_gga: Optional[GGA] = None
        self._last_rmc: Optional[RMC] = None

        self.has_fix = False

        self.current_utc = None
        self.current_log_line = None
        self.current_sat_count = None
        self.current_speed = None
        self.fix_quality = None
        self.local_datum = None
        self.reference_datum = None


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
            if self._last_gga is not None:
                raise GPSStateException("Two GGA without a RMC")
            else:
                self._last_gga = msg

        if type(msg) is RMC:
            if self._last_rmc is not None:
                raise GPSStateException("Two RMC without a GGA")
            else:
                self._last_rmc = msg

        if type(msg) is DTM:
            self.local_datum = msg.local_datum
            self.reference_datum = msg.reference_datum

        if self._last_gga and self._last_rmc:
            if self._last_gga.utc_time != self._last_rmc.utc_time:  # these are comparable
                raise GPSStateException("GGA and RMC out of sync!?")

            # 2011-12-31T23:59:59Z
            line_utc = "{}T{}Z".format(self._last_rmc.utc_date, self._last_rmc.utc_time)

            # time,lat,long,altitude,speed,sats,hdop
            line = "{},{},{},{:.2f},{:.2f},{},{}".format(
                line_utc,
                self._last_gga.latitude,
                self._last_gga.longitude,
                self._last_gga.altitude,
                self._last_rmc.speed_kmh,
                self._last_gga.satellites,
                self._last_gga.hdop
            )

            self.fix_quality = self._last_gga.fix_quality

            if self._last_gga.hdop < 100 and self._last_gga.satellites > 3:
                self.has_fix = True
                self.current_utc = line_utc
                self.current_log_line = line
                self.current_sat_count = self._last_gga.satellites
                self.current_speed = self._last_rmc.speed_kmh
            else:
                self.has_fix = False

            self._last_gga = None
            self._last_rmc = None

            # Update the UI
            return True

        # Don't update the UI
        return False