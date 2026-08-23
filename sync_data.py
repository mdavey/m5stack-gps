#!/usr/bin/env python3
"""Sync all files from the device's transfer web API into ./data/.

Reads the device IP from .last_ip (asks for it and saves it if missing).
For every file on the device that we don't already have (or whose local
size doesn't match), fetch its expected CRC32, download it, verify size
and CRC32.  Files are only removed from the device when --delete is
given.  When everything synced cleanly the device is told to reset.

Every ./data/*.csv also gets a matching .gpx (single track) generated next
to it - created if missing or older than the csv.
"""

import argparse
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET
import zlib
from http.client import HTTPException
from urllib import error, parse, request

IP_FILE = "sync_data.last_ip"
DATA_DIR = "data"
PORT = 5000
TIMEOUT = 30
CHUNK_SIZE = 8192

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

CSV_COLUMNS = ["timestamp", "latitude", "longitude", "altitude", "speed",
               "num_satellites", "hdop"]


def ask_for_ip():
    try:
        ip = input("Device IP address: ").strip()
    except EOFError:
        sys.exit("\nNo IP address available on stdin, aborting.")
    if not ip:
        sys.exit("No IP address given, aborting.")
    with open(IP_FILE, "w+") as f:
        f.write(ip + "\n")
    return ip


def load_ip():
    if os.path.exists(IP_FILE):
        with open(IP_FILE) as f:
            ip = f.read().strip()
        if ip:
            print("Using device IP {} (from {})".format(ip, IP_FILE))
            return ip
    return ask_for_ip()


def open_request(ip, path, method="GET", timeout=TIMEOUT):
    url = "http://{}:{}{}".format(ip, PORT, path)
    req = request.Request(url, method=method)
    return request.urlopen(req, timeout=timeout)


def local_path_for(filename: str):
    # Device serves flat files from the SD root; never let a name escape DATA_DIR
    if filename != os.path.basename(filename) or filename in (".", "..", ""):
        raise ValueError("unsafe filename from device: {!r}".format(filename))
    return os.path.join(DATA_DIR, filename)


def get_file_list(ip):
    for attempt in range(3):
        try:
            with open_request(ip, "/list") as resp:
                body = resp.read()
            listing = json.loads(body.decode())
            return [entry for entry in listing
                    if "filename" in entry and "size" in entry]
        except (error.URLError, OSError, HTTPException) as e:
            if attempt == 2:
                sys.exit("Could not get file list from {}: {}".format(ip, e))
            print("Could not reach device at {} ({}), try again.".format(ip, e))
            ip = ask_for_ip()
    return []  # unreachable


def fetch_expected_crc(ip: str, filename: str):
    with open_request(ip, "/crc32/" + parse.quote(filename)) as resp:
        return int(resp.read().decode().strip(), 16) & 0xFFFFFFFF


def download_file(ip: str, filename: str, dest: str):
    """Stream a file to dest + '.part', return (size, crc32) of what landed."""
    size = 0
    crc = 0
    part = dest + ".part"
    with open_request(ip, "/get/" + parse.quote(filename)) as resp, \
            open(part, "wb") as f:
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)
            crc = zlib.crc32(chunk, crc)
    return size, crc & 0xFFFFFFFF


def crc32_of_file(path: str):
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            crc = zlib.crc32(chunk, crc)
    return crc & 0xFFFFFFFF


def delete_on_device(ip, filename):
    with open_request(ip, "/delete/" + parse.quote(filename),
                      method="DELETE") as resp:
        resp.read()


def reset_device(ip):
    try:
        with open_request(ip, "/reset", timeout=3) as resp:
            resp.read()
    except (error.URLError, OSError, HTTPException):
        # The device soft-resets before answering; a dropped connection
        # here means it got the message.
        print("(connection closed by device during reset - that's expected)")
    print("Device is resetting.  Sync complete.")


def _add_point_element(parent, tag, raw, cast):
    """Append <tag>raw</tag> when raw is a non-empty value cast can parse."""
    if raw is None:
        return
    raw = str(raw).strip()
    if not raw:
        return
    try:
        cast(raw)
    except ValueError:
        return
    ET.SubElement(parent, "{%s}%s" % (GPX_NS, tag)).text = raw


def csv_to_gpx(csv_path: str, gpx_path: str):
    """Convert one logger csv into a single-track GPX 1.1 file.

    Values are copied through verbatim from the csv so no precision is
    lost.  Rows without usable lat/lon (e.g. a torn final line from a
    device that lost power mid-write) are skipped.  Returns
    (points_written, rows_skipped); nothing is written when there are
    no usable points.
    """
    name = os.path.splitext(os.path.basename(csv_path))[0]

    ET.register_namespace("", GPX_NS)
    ET.register_namespace("xsi", XSI_NS)
    gpx = ET.Element("{%s}gpx" % GPX_NS, {
        "version": "1.1",
        "creator": "m5stack gps logger (sync_data.py)",
        "{%s}schemaLocation" % XSI_NS:
            "http://www.topografix.com/GPX/1/1 "
            "http://www.topografix.com/GPX/1/1/gpx.xsd",
    })
    metadata = ET.SubElement(gpx, "{%s}metadata" % GPX_NS)
    ET.SubElement(metadata, "{%s}name" % GPX_NS).text = name
    ET.SubElement(metadata, "{%s}desc" % GPX_NS).text = \
        "GPS track from m5stack GPS logger (converted from {})".format(
            os.path.basename(csv_path))
    trk = ET.SubElement(gpx, "{%s}trk" % GPX_NS)
    ET.SubElement(trk, "{%s}name" % GPX_NS).text = name
    trkseg = ET.SubElement(trk, "{%s}trkseg" % GPX_NS)

    points = 0
    skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        # older files were written without the header row
        has_header = f.readline().split(",", 1)[0].strip().lower() == "timestamp"
        f.seek(0)
        reader = csv.DictReader(
            f, fieldnames=None if has_header else CSV_COLUMNS)
        for row in reader:
            lat = (row.get("latitude") or "").strip()
            lon = (row.get("longitude") or "").strip()
            try:
                float(lat)
                float(lon)
            except ValueError:
                skipped += 1
                continue
            trkpt = ET.SubElement(trkseg, "{%s}trkpt" % GPX_NS,
                                  lat=lat, lon=lon)
            _add_point_element(trkpt, "ele", row.get("altitude"), float)
            timestamp = (row.get("timestamp") or "").strip()
            if timestamp:
                ET.SubElement(trkpt, "{%s}time" % GPX_NS).text = timestamp
            _add_point_element(trkpt, "sat", row.get("num_satellites"), int)
            _add_point_element(trkpt, "hdop", row.get("hdop"), float)
            points += 1

    if not points:
        return 0, skipped

    tree = ET.ElementTree(gpx)
    if hasattr(ET, "indent"):  # Python 3.9+
        ET.indent(tree)
    tmp = gpx_path + ".tmp"
    tree.write(tmp, encoding="UTF-8", xml_declaration=True)
    os.replace(tmp, gpx_path)
    return points, skipped


def convert_local_csvs():
    """Make sure every ./data/*.csv has a matching, up-to-date .gpx."""
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.lower().endswith(".csv"):
            continue
        csv_path = os.path.join(DATA_DIR, name)
        if not os.path.isfile(csv_path):
            continue
        gpx_path = os.path.splitext(csv_path)[0] + ".gpx"
        if os.path.exists(gpx_path) and \
                os.path.getmtime(gpx_path) >= os.path.getmtime(csv_path):
            continue
        try:
            points, skipped = csv_to_gpx(csv_path, gpx_path)
        except OSError as e:
            print("{}: GPX conversion FAILED - {}".format(name, e))
            continue
        if points:
            print("{}: wrote {} ({:,} track points{})".format(
                name, os.path.basename(gpx_path), points,
                ", {:,} bad row(s) skipped".format(skipped)
                if skipped else ""))
        else:
            print("{}: no usable track points, no GPX written "
                  "({:,} row(s) skipped)".format(name, skipped))


def main():
    parser = argparse.ArgumentParser(
        description="Sync all files from the GPS logger device into ./data/.")
    parser.add_argument("--delete", action="store_true",
                        help="delete files from the device once they have "
                             "been verified locally")
    opts = parser.parse_args()

    ip = load_ip()
    listing = get_file_list(ip)
    print("{} file(s) on device.".format(len(listing)))

    os.makedirs(DATA_DIR, exist_ok=True)

    # 2. Work out which files we don't have (or that look wrong locally)
    needed = []
    failures = 0
    for entry in listing:
        name = entry["filename"]
        size = entry["size"]
        path = local_path_for(name)
        if not os.path.exists(path):
            needed.append((name, size))
        elif os.path.getsize(path) != size:
            print("{}: local size mismatch, re-downloading".format(name))
            needed.append((name, size))
        elif opts.delete:
            # We're about to remove it from the device, so make sure the
            # local copy really matches first
            try:
                if crc32_of_file(path) == fetch_expected_crc(ip, name):
                    delete_on_device(ip, name)
                    print("{}: local copy verified, deleted from device"
                          .format(name))
                else:
                    print("{}: local copy differs, re-downloading".format(name))
                    needed.append((name, size))
            except (error.URLError, OSError, HTTPException) as e:
                print("{}: FAILED - {}".format(name, e))
                failures += 1
        else:
            print("{}: already have it".format(name))

    if not needed:
        print("Nothing to download.")

    # 3-6: crc, download, verify, (delete remote)
    for name, size in needed:
        path = local_path_for(name)
        try:
            expected_crc = fetch_expected_crc(ip, name)
            got_size, got_crc = download_file(ip, name, path)

            if got_size != size:
                raise ValueError("size mismatch: expected {} bytes, got {}"
                                 .format(size, got_size))

            if got_crc != expected_crc:
                raise ValueError("crc32 mismatch: expected {:08x}, got {:08x}"
                                 .format(expected_crc, got_crc))

            os.replace(path + ".part", path)
            print("{}: downloaded and verified ({} bytes)".format(name, size))

            if opts.delete:
                delete_on_device(ip, name)
                print("{}: deleted from device".format(name))
        except (error.URLError, OSError, HTTPException, ValueError) as e:
            if os.path.exists(path + ".part"):
                os.remove(path + ".part")
            print("{}: FAILED - {}".format(name, e))
            failures += 1

    # GPX for every local csv (freshly downloaded ones included)
    convert_local_csvs()

    if not opts.delete and listing:
        print("Note: files were left on the device - re-run with --delete "
              "to clean them up once you're happy with the local copies.")

    if failures:
        print("{} file(s) failed; leaving them on the device and NOT "
              "resetting it.  Re-run to retry.".format(failures))
        sys.exit(1)

    # 7. All good - tell the device we're done
    reset_device(ip)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
