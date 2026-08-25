
class NanoDegrees:
    _scale = 1000000000

    def __init__(self, decimal_degrees_str: str, direction: str):
        self._decimal_degrees_str = decimal_degrees_str.strip()
        self._direction = direction.strip()

        try:
            self._nano_degrees = 0
            self._parse()
        except ValueError:
            pass

    def _parse(self):
        if "." in self._decimal_degrees_str:
            left, right = self._decimal_degrees_str.split(".")
        else:
            left, right = self._decimal_degrees_str, ""

        degrees = int(left[:-2])
        minutes = int(left[-2:])

        self._nano_degrees =  degrees * self._scale
        self._nano_degrees += (minutes * self._scale) // 60

        if right:
            frac_min = int(right)
            # Divisor accounts for the number of decimal places in the string
            # e.g., if right is "50556800", length is 8, divisor is 60 * 10^8
            divisor = 60 * (10 ** len(right))
            self._nano_degrees += (frac_min * self._scale) // divisor

        if self._direction in ('S', 'W'):
            self._nano_degrees = -self._nano_degrees

    def __str__(self):
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


if __name__ == "__main__":
    a,b = "3758.50614713", "S"
    lat = NanoDegrees(a, b)
    print(repr(lat))