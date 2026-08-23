from collections import namedtuple


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
