from nano_degrees import NanoDegrees


class UtcTime:
    def __init__(self, hour: int, min: int, sec: int):
        self.hour = hour
        self.min = min
        self.sec = sec

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return "{:02}:{:02}:{:02}".format(self.hour, self.min, self.sec)

    def __repr__(self):
        return "UtcTime(hour={}, min={}, sec={})".format(self.hour, self.min, self.sec)


class UtcDate:
    def __init__(self, year: int, month: int, day: int):
        self.year = year
        self.month = month
        self.day = day

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return "{:04}:{:02}:{:02}".format(self.year, self.month, self.day)

    def __repr__(self):
        return "UtcDate(year={}, month={}, day={})".format(self.year, self.month, self.day)


class NMEAMessage:
    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        vals = []
        for key, value in vars(self).items():
            vals.append("{}={}".format(key, repr(value)))
        return ", ".join(vals)


class GGA(NMEAMessage):
    def __init__(self, utc_time: UtcTime, latitude: NanoDegrees, longitude: NanoDegrees, fix_quality: int, satellites: int, hdop: float, altitude: float):
        self.utc_time = utc_time
        self.latitude = latitude
        self.longitude = longitude
        self.fix_quality = fix_quality
        self.satellites = satellites
        self.hdop = hdop
        self.altitude = altitude


class RMC(NMEAMessage):
    def __init__(self, utc_time: UtcTime, utc_date: UtcDate, status: str, latitude: NanoDegrees, longitude: NanoDegrees, speed_kmh: float, track: float):
        self.utc_time = utc_time
        self.utc_date = utc_date
        self.status = status
        self.latitude = latitude
        self.longitude = longitude
        self.speed_kmh = speed_kmh
        self.track = track


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
        hour = safe_int(val[0:2]),
        min  = safe_int(val[2:4]),
        sec  = safe_int(val[4:6])
    )


def parse_utc_date(val: str):
    # ddmmyy
    return UtcDate(
        year  = 2000 + safe_int(val[4:6]),
        month = safe_int(val[2:4]),
        day   = safe_int(val[0:2])
    )


def parse_gga(parts: list):
    # $--GGA,hhmmss.ss,llll.ll,a,yyyyy.yy,a,x,xx,x.x,x.x,M,x.x,M,x.x,xxxx*hh
    return GGA(
        utc_time    = parse_utc_time(parts[1]),
        latitude    = NanoDegrees(parts[2], parts[3]),
        longitude   = NanoDegrees(parts[4], parts[5]),
        fix_quality = safe_int(parts[6]),
        satellites  = safe_int(parts[7]),
        hdop        = safe_float(parts[8]),
        altitude    = safe_float(parts[9])
    )


def parse_rmc(parts: list):
    # $--RMC,hhmmss.ss,A,llll.ll,a,yyyyy.yy,a,x.x,x.x,ddmmyy,x.x,a,a*hh
    return RMC(
        utc_time = parse_utc_time(parts[1]),
        utc_date  = parse_utc_date(parts[9]),
        status    = parts[2],
        latitude  = NanoDegrees(parts[3], parts[4]),
        longitude = NanoDegrees(parts[5], parts[6]),
        speed_kmh = safe_float(parts[7])*1.852,  # knots to kmh
        track     = safe_float(parts[8])
    )


def parse_nmea(raw_sentence: str):
    """Clean the raw string, identify its type, and route to the correct parser."""
    if not raw_sentence.startswith('$'): return None

    # Strip any trailing carriage returns, newlines, and the checksum split
    clean_line = raw_sentence.strip().split('*')[0]
    parts = clean_line.split(',')

    # Extract sentence identifier (e.g., GPGGA, GNRMC -> GGA, RMC)
    msg_type = parts[0][3:] if len(parts[0]) > 3 else ""

    if msg_type == "GGA":   return parse_gga(parts)
    elif msg_type == "RMC": return parse_rmc(parts)
    return None


if __name__ == "__main__":
    print(parse_nmea("$GNGGA,082228.00,3758.50556800,S,14511.93875408,E,2,28,0.5,49.1963,M,4.6768,M,2.0,0122"))