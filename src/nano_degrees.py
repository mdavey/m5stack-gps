
class NanoDegrees:
    _scale = 1000000000

    # nmea_degrees must match:  hhmm.ssss   or  hhhmm.ssss
    # direction must be 'N', 'S', 'E', 'W'
    def __init__(self, nmea_degrees: str, direction: str):
        self._nmea_degrees_str = nmea_degrees.strip()
        self._direction = direction.strip()
        self._is_valid = True

        try:
            self._nano_degrees = 0
            self._parse()
        except ValueError:
            pass

    def is_valid(self) -> bool:
        return self._is_valid

    def _parse(self):
        if "." not in self._nmea_degrees_str:
            self._is_valid = False
            return

        if self._direction not in ('S', 'W', 'N', 'E'):
            self._is_valid = False
            return

        left, right = self._nmea_degrees_str.split(".")

        degrees = int(left[:-2])
        minutes = int(left[-2:])

        self._nano_degrees =  degrees * self._scale
        self._nano_degrees += (minutes * self._scale) // 60

        frac_min = int(right)
        # Divisor accounts for the number of decimal places in the string
        # e.g., if right is "50556800", length is 8, divisor is 60 * 10^8
        divisor = 60 * (10 ** len(right))
        self._nano_degrees += (frac_min * self._scale) // divisor

        if self._direction in ('S', 'W'):
            self._nano_degrees = -self._nano_degrees

    def to_float(self):
        return float(str(self))

    def __str__(self):
        if not self.is_valid():
            return "0.0"

        sign = "-" if self._nano_degrees < 0 else ""
        nano = abs(self._nano_degrees)
        deg_str = str(nano // self._scale)
        frac_str = str(nano % self._scale)

        # pad with leading zeros to ensure it is exactly 9 digits long
        if len(frac_str) < 9:
            frac_str = ("0" * (9 - len(frac_str))) + frac_str

        return "{}{}.{}".format(sign, deg_str, frac_str)

    def __repr__(self):
        return "NanoDegree({})".format(str(self))

    def __eq__(self, other):
        return str(self) == str(other)


if __name__ == "__main__":
    import math

    tests = [
        ("4158.8441",  "N", 41.980735),
        ("3352.1292",  "S", -33.868820),
        ("0005.3674",  "N", 0.08945667),
        ("15112.5578", "E", 151.209296),
        ("00007.6687", "W", -0.127812),
        ("00434.0734", "E", 4.567890),
        ("00434.0734", "Q", 0.0),
        ("04.04",      "E", 0.0),
    ]

    for nmea_degree, nmea_hemisphere, correct_decimal_degrees in tests:
        decimal_degrees = NanoDegrees(nmea_degree, nmea_hemisphere)

        if math.isclose(decimal_degrees.to_float(), correct_decimal_degrees, abs_tol=0.000001):
            print(f"PASS:  {decimal_degrees} is equal {correct_decimal_degrees}")
        else:
            print(f"FAIL:  {decimal_degrees} is not equal {correct_decimal_degrees}")


