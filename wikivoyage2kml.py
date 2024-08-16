#!/usr/bin/env python3

"""Wikivoyage2KML: Script to generate kml/kmz files for maps.me from Wikivoyage articles"""

import argparse
import html
import os
import sys
import time
from typing import Final
from zipfile import ZipFile

import requests
import wikitextparser as wtp
from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim
from requests.exceptions import ConnectionError

__author__ = "Jorge Mira"
__copyright__ = "Copyright 2020"
__credits__ = ["Jorge Mira"]
__license__ = "Apache License 2.0"
__version__ = "0.1.0"
__maintainer__ = "Jorge Mira"
__email__ = "jorge.mira.yague@gmail.com"
__status__ = "Dev"

OUTPUT_FILENAME: Final[str] = "{destination} ({language}) - Wikivoyage2KML"
KML_EXTENSION: Final[str] = "kml"
KMZ_EXTENSION: Final[str] = "kmz"
WIKI_URL: Final[str] = "https://{language}.wikivoyage.org/w/api.php"

MARKER_TYPES = {
    "do": {"color": "teal", "icon": "Entertainment"},
    "go": {"color": "brown", "icon": "Transport"},
    "buy": {"color": "pink", "icon": "Shop"},
    "eat": {"color": "red", "icon": "Food"},
    "see": {"color": "green", "icon": "Sights"},
    "drink": {"color": "yellow", "icon": "Bar"},
    "sleep": {"color": "blue", "icon": "Hotel"},
    "default": {"color": "gray", "icon": "None"},
}


def get_wikicode(destination: str, language: str) -> str:
    """Get the wikicode of a wikivoyage article for the given destination"""
    try:
        response = requests.get(
            WIKI_URL.format(language=language),
            params={
                "action": "query",
                "format": "json",
                "titles": destination,
                "prop": "revisions",
                "rvprop": "content",
            },
        ).json()
    except ConnectionError:
        sys.exit(f"Error trying to get page '{destination}' in https://{language}.wikivoyage.org/")

    page = next(iter(response["query"]["pages"].values()))
    if "missing" in page:
        sys.exit(f"Page for '{destination}' does not exist in https://{language}.wikivoyage.org/")
    wikicode = str(page["revisions"][0]["*"])

    return wikicode


def a(href: str, text: str) -> str:
    return f"<a href='{href}'>{text}</a>"


def b(text: str) -> str:
    return f"<b>{text}</b>"


def marker_to_kml(marker: dict[str, str]) -> str:
    """Create KML code for a marker"""
    contents = []
    with open("templates/Placemark.kml") as f:
        tpl = f.read()

    # TODO: Fix images to get proper links
    # if 'image' in marker:
    #     contents.append("<img src='{img}'></img>".format(img=marker['image']))
    if "added_location" in marker:
        contents.append(
            b("WARNING: ") + "Location has been added automatically, marker may not be correct"
        )
    if "url" in marker:
        contents.append(b("URL: ") + a(marker["url"], marker["url"]))
    if "phone" in marker:
        contents.append(b("Phone number: ") + a("tel:" + marker["phone"], marker["phone"]))
    if "email" in marker:
        contents.append(b("Email: ") + a("mailto:" + marker["email"], marker["email"]))
    if "address" in marker:
        contents.append(b("Address: ") + marker["address"])
    if "directions" in marker:
        contents.append(b("Directions: ") + marker["directions"])
    if "hours" in marker:
        contents.append(b("Opening hours: ") + marker["hours"])
    if "content" in marker:
        contents.append(b("Place description:"))
        contents.append(marker["content"])

    kml = tpl.format(
        name=marker["name"],
        description="<br/>".join(contents),
        color=MARKER_TYPES[marker["type"]]["color"],
        coordinates=marker["long"] + ", " + marker["lat"],
        icon=MARKER_TYPES[marker["type"]]["icon"],
    )

    return kml


def valid_coordinates(marker: dict[str, str]) -> bool:
    """Checks wether coordinates are valid: a number between 90 and -90 for latitude and -180 and
    180 for longitude"""
    try:
        if abs(float(marker["long"])) > 180 or abs(float(marker["lat"])) > 90:
            raise ValueError
    except (KeyError, ValueError):
        return False

    return True


def extract_markers(
    wikicode: str, destination: str, add_locations: bool = False
) -> list[dict[str, str]]:
    """Extracts the markers for a given wikicode text"""
    parsed = wtp.parse(wikicode)
    markers = []

    for t in parsed.templates:
        marker = {
            a.name.strip(): html.escape(a.value.strip()) for a in t.arguments if a.value.strip()
        }

        mtype = t.name.strip()
        if mtype in ["marker", "listing"]:
            mtype = marker.get("type", "default")
        if mtype not in list(MARKER_TYPES):
            mtype = "default"
        marker["type"] = mtype

        if "name" not in marker:  # Discard invalid markers
            continue

        if valid_coordinates(marker):
            markers.append(marker)
        elif add_locations:
            marker = add_location(marker, destination)
            if valid_coordinates(marker):
                markers.append(marker)

    return markers


def add_location(marker: dict[str, str], destination: str) -> dict[str, str]:
    """Try to add GPS coordinates to a marker in the given destination from Nominatim"""
    geolocator = Nominatim(user_agent="wikivoyage2klm")
    location = None

    if marker.get("address", None):
        time.sleep(1)  # Comply with Nominatim usage policy of one request per second

        try:
            location = geolocator.geocode(query={"street": marker["address"], "city": destination})
        except GeocoderServiceError:
            print("Marker for '{}' not added because Nominatim error".format(marker["name"]))
            time.sleep(10)  # Too many requests to Nominatim, taking a rest

        if location:  # Location found
            marker["long"] = str(location.longitude)
            marker["lat"] = str(location.latitude)
            marker["added_location"] = "yes"
            print("Marker for '{}' added using automatic location".format(marker["name"]))
        else:
            print("Marker for '{}' could not be found on Nominatim".format(marker["name"]))

    else:
        print("Marker for '{}' Not added because address is missing".format(marker["name"]))

    return marker


def create_kml(destination: str, add_locations: bool, language: str) -> str:
    """Creates the kml document for the given destination"""
    wikicode = get_wikicode(destination, language)
    markers = extract_markers(wikicode, destination, add_locations)
    markers_kml = "\n".join(marker_to_kml(m) for m in markers)

    with open("templates/Wikivoyage2KML.kml") as f:
        tpl = f.read()
    kml = tpl.format(name=destination, placemarks=markers_kml)

    print(f"{len(markers)} markers added for destination: {destination}")

    return kml


def main() -> None:
    # Args parsing
    parser = argparse.ArgumentParser(
        description="Create KML/KMZ files for maps.me from Wikivoyage articles"
    )
    parser.add_argument("destination", help="Destination name")
    parser.add_argument(
        "-z",
        "--kmz",
        action="store_true",
        default=False,
        help="Save output to KMZ format",
    )
    parser.add_argument(
        "-a", "--add", action="store_true", default=False, help="Add missing locations"
    )
    parser.add_argument(
        "-l",
        "--language",
        default="en",
        help="Language of the Wikivoyage article, defaults to en",
    )
    args = parser.parse_args()

    kml = create_kml(args.destination, args.add, args.language)

    filename = OUTPUT_FILENAME.format(destination=args.destination, language=args.language)

    # Output to KML
    kml_file_name = f"{filename}.{KML_EXTENSION}"
    with open(kml_file_name, "w") as file:
        file.write(kml)

    # Output to KMZ
    if args.kmz:
        with ZipFile(f"{filename}.{KMZ_EXTENSION}", "w") as zfile:
            zfile.write(kml_file_name)
        os.remove(kml_file_name)


if __name__ == "__main__":
    main()
