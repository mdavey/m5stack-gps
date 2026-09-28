import traceback

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
        return "{:04}-{:02}-{:02}".format(self.year, self.month, self.day)

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


class SATSINFOA(NMEAMessage): # I know it's not NMEA...
    def __init__(self, number_satellites: int):
        self.number_satellites = number_satellites


class DTM(NMEAMessage):
    def __init__(self, local_datum: str, local_sub_datum: str, latitude_offset: float, latitude_dir: str, longitude_offset: float, longitude_dir: str, altitude_offset: float, reference_datum: str):
        self.local_datum = local_datum
        self.local_sub_datum = local_sub_datum
        self.latitude_offset = latitude_offset
        self.latitude_dir = latitude_dir
        self.longitude_offset = longitude_offset
        self.longitude_dir = longitude_dir
        self.altitude_offset = altitude_offset
        self.reference_datum = reference_datum


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


def parse_satsinfoa(complete_string: str):
    def stream_data(text: str):
        start = 0
        while True:
            end = text.find(",", start)
            if end == -1:
                yield text[start:]
                break
            yield text[start:end]
            start = end + 1

    (header, details) = complete_string.split(';')

    try:
        items = stream_data(details)
        number_satellites = safe_int(next(items))     # Number of tracked satellites
        version_number = safe_int(next(items)) # Version number, default = 2

        next(items) # Reserved
        next(items) # Reserved
        next(items) # Reserved

        frequency_flag = safe_int(next(items))  # Frequency flag

        # I really don't care about frequencies and prns right now
        return SATSINFOA(
            number_satellites = number_satellites,
        )

    except StopIteration as e:
        traceback.print_exception(e)

    return None


def parse_dtm(parts: list):
    return DTM(
        local_datum      = parts[1],
        local_sub_datum  = parts[2],
        latitude_offset  = safe_float(parts[3]),
        latitude_dir     = parts[4],
        longitude_offset = safe_float(parts[5]),
        longitude_dir    = parts[6],
        altitude_offset  = safe_float(parts[7]),
        reference_datum  = parts[8]
    )


def parse_nmea(raw_sentence: str):
    """Clean the raw string, identify its type, and route to the correct parser."""
    if not raw_sentence.startswith('$') and not raw_sentence.startswith('#'): return None

    # Strip any trailing carriage returns, newlines, and the checksum split
    clean_line = raw_sentence.strip().split('*')[0]

    if clean_line.startswith("$GNGGA"):       return parse_gga(clean_line.split(','))
    elif clean_line.startswith("$GNRMC"):     return parse_rmc(clean_line.split(','))
    elif clean_line.startswith("$GNDTM"):     return parse_dtm(clean_line.split(','))
    elif clean_line.startswith("#SATSINFOA"): return parse_satsinfoa(clean_line)

    return None


if __name__ == "__main__":
    # print(parse_nmea("$GNGGA,082228.00,3758.50556800,S,14511.93875408,E,2,28,0.5,49.1963,M,4.6768,M,2.0,0122"))
    # SATS_INFO = """#SATSINFOA,96,GPS,FINE,2215,367199000,0,0,18,16;50,2,0,0,0,63,2,302,51,0,45,0,2,0,42,9,2,4,48,17,0,37,0,3,0,43,14,3,0,39,9,3,5,225,14,0,42,0,2,0,37,9,2,6,35,64,0,47,0,3,0,52,14,3,0,48,9,3,9,80,33,0,42,0,3,0,44,14,3,0,40,9,3,11,300,56,0,46,0,3,0,50,14,3,0,46,9,3,12,277,37,0,42,0,2,0,41,9,2,17,134,31,0,44,0,2,0,41,9,2,19,130,53,0,46,0,2,0,43,9,2,20,232,47,0,46,0,2,0,42,9,2,25,316,15,0,38,0,3,0,45,14,3,0,40,9,3,28,0,0,0,37,0,2,0,31,9,2,194,170,8,5,38,0,3,5,41,14,3,5,37,9,3,195,112,67,5,45,0,3,5,49,14,3,5,47,9,3,196,132,61,5,42,0,3,5,48,14,3,5,46,9,3,199,163,43,5,36,0,3,5,46,14,3,5,44,9,3,39,116,64,1,43,0,2,1,49,5,2,55,316,30,1,43,0,2,1,46,5,2,52,242,10,1,39,0,2,1,39,5,2,38,35,28,1,40,0,2,1,41,5,2,61,93,29,1,42,0,2,1,45,5,2,54,22,62,1,47,0,2,1,50,5,2,40,180,27,1,42,0,2,1,45,5,2,46,342,4,1,34,0,2,1,39,5,2,11,93,61,4,33,0,3,4,52,17,3,4,50,21,3,42,114,67,4,34,0,4,4,51,21,4,4,48,8,4,4,49,12,4,2,224,33,4,45,17,2,4,41,21,2,10,214,52,4,29,0,3,4,46,17,3,4,45,21,3,28,306,28,4,29,0,4,4,44,21,4,4,41,8,4,4,42,12,4,40,180,42,4,31,0,4,4,44,21,4,4,43,8,4,4,43,12,4,8,289,63,4,31,0,3,4,48,17,3,4,46,21,3,43,8,79,4,36,0,4,4,51,21,4,4,47,8,4,4,50,12,4,7,197,46,4,28,0,3,4,47,17,3,4,45,21,3,21,47,30,4,31,0,4,4,43,21,4,4,43,8,4,4,43,12,4,23,243,4,4,24,8,2,4,30,12,2,4,123,26,4,43,17,2,4,41,21,2,5,248,16,4,38,17,2,4,35,21,2,1,139,36,4,28,0,3,4,46,17,3,4,43,21,3,34,111,40,4,32,0,4,4,48,21,4,4,44,8,4,4,41,12,4,38,317,74,4,35,0,4,4,49,21,4,4,47,8,4,4,49,12,4,2,311,18,3,39,2,3,3,45,17,3,3,43,12,3,4,136,38,3,43,2,3,3,48,17,3,3,46,12,3,10,0,0,3,47,2,3,3,53,17,3,3,50,12,3,11,325,63,3,43,2,3,3,47,17,3,3,45,12,3,12,71,45,3,42,2,3,3,45,17,3,3,42,12,3,19,63,32,3,40,2,3,3,40,17,3,3,38,12,3,24,203,15,3,37,2,3,3,43,17,3,3,40,12,3,25,260,32,3,42,2,3,3,46,17,3,3,44,12,3,9,181,7,3,37,2,3,3,41,17,3,3,39,12,3,36,286,19,3,34,2,3,3,42,17,3,3,38,12,3*a79d3813"""
    # print(parse_nmea(SATS_INFO))

    print(parse_nmea("$GNDTM,W84,,0.0,N,0.0,E,0.0,W84*71"))