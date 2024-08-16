#!/usr/bin/env python3

"""Wikivoyage2KML: Script to generate kml/kmz files for maps.me from Wikivoyage articles"""

import argparse
import html
import os
import sys
import time
from dataclasses import dataclass
from typing import Final, NewType
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


@dataclass
class Settings:
    destination: str
    language: str
    kmz: bool
    add: bool


@dataclass
class MarkerType:
    color: str
    icon: str


Marker = NewType("Marker", dict[str, str])

OUTPUT_FILENAME: Final[str] = "{destination} ({language}) - Wikivoyage2KML"
KML_EXTENSION: Final[str] = "kml"
KMZ_EXTENSION: Final[str] = "kmz"
WIKI_URL: Final[str] = "https://{language}.wikivoyage.org/w/api.php"
KML_TEMPLATE: Final[str] = "templates/Wikivoyage2KML.kml"
MARKER_TEMPLATE: Final[str] = "templates/Placemark.kml"
MARKER_TYPES: Final[dict[str, MarkerType]] = {
    "do": MarkerType(color="teal", icon="Entertainment"),
    "go": MarkerType(color="brown", icon="Transport"),
    "buy": MarkerType(color="pink", icon="Shop"),
    "eat": MarkerType(color="red", icon="Food"),
    "see": MarkerType(color="green", icon="Sights"),
    "drink": MarkerType(color="yellow", icon="Bar"),
    "sleep": MarkerType(color="blue", icon="Hotel"),
    "default": MarkerType(color="gray", icon="None"),
}


def get_wikicode(settings: Settings) -> str:
    """Get the wikicode of a wikivoyage article for the given destination"""
    try:
        response = requests.get(
            WIKI_URL.format(language=settings.language),
            params={
                "action": "query",
                "format": "json",
                "titles": settings.destination,
                "prop": "revisions",
                "rvprop": "content",
            },
        )
    except ConnectionError:
        sys.exit(
            f"Error trying to get page '{settings.destination}' in "
            f"https://{settings.language}.wikivoyage.org/"
        )
    data = response.json()
    page = next(iter(data["query"]["pages"].values()))
    if "missing" in page:
        sys.exit(
            f"Page for '{settings.destination}' does not exist in "
            f"https://{settings.language}.wikivoyage.org/"
        )
    wikicode = str(page["revisions"][0]["*"])

    return wikicode


def a(href: str, text: str) -> str:
    return f"<a href='{href}'>{text}</a>"


def b(text: str) -> str:
    return f"<b>{text}</b>"


def marker_to_kml(marker: Marker, template: str) -> str:
    """Create KML code for a marker"""
    contents = []

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

    marker_type = MARKER_TYPES[marker["type"]]
    kml = template.format(
        name=marker["name"],
        description="<br/>".join(contents),
        color=marker_type.color,
        coordinates=marker["long"] + ", " + marker["lat"],
        icon=marker_type.icon,
    )

    return kml


def valid_coordinates(marker: Marker) -> bool:
    """Checks wether coordinates are valid: a number between 90 and -90 for latitude and -180 and
    180 for longitude"""
    try:
        if abs(float(marker["long"])) > 180 or abs(float(marker["lat"])) > 90:
            raise ValueError
    except (KeyError, ValueError):
        return False

    return True


def extract_markers(wikicode: str, settings: Settings) -> list[Marker]:
    """Extracts the markers for a given wikicode text"""
    parsed = wtp.parse(wikicode)
    markers = []

    for t in parsed.templates:
        marker = Marker(
            {a.name.strip(): html.escape(a.value.strip()) for a in t.arguments if a.value.strip()}
        )

        mtype = t.name.strip()
        if mtype in ["marker", "listing"]:
            mtype = marker.get("type", "default")
        if mtype not in MARKER_TYPES:
            mtype = "default"
        marker["type"] = mtype

        if "name" not in marker:  # Discard invalid markers
            continue

        if valid_coordinates(marker):
            markers.append(marker)
        elif settings.add and (marker_with_location := add_location(marker, settings.destination)):
            markers.append(marker_with_location)

    return markers


def add_location(marker: Marker, destination: str) -> Marker | None:
    """Try to add GPS coordinates to a marker in the given destination from Nominatim"""
    geolocator = Nominatim(user_agent="wikivoyage2klm")
    location = None

    if marker.get("address", None):
        time.sleep(1)  # Comply with Nominatim usage policy of one request per second

        try:
            location = geolocator.geocode(query={"street": marker["address"], "city": destination})
        except GeocoderServiceError:
            print("Marker for '{}' not added because Nominatim error".format(marker["name"]))

        if location:  # Location found
            new_marker = Marker(dict(marker))
            new_marker["long"] = str(location.longitude)
            new_marker["lat"] = str(location.latitude)
            new_marker["added_location"] = "yes"
            if valid_coordinates(new_marker):
                print("Marker for '{}' added using automatic location".format(new_marker["name"]))
                return new_marker
            else:
                print("Marker for '{}' has invalid coordinates".format(new_marker["name"]))
        else:
            print("Marker for '{}' could not be found on Nominatim".format(marker["name"]))
    else:
        print("Marker for '{}' Not added because address is missing".format(marker["name"]))

    return None


def create_kml(settings: Settings) -> str:
    """Creates the kml document for the given destination"""
    wikicode = get_wikicode(settings)

    markers = extract_markers(wikicode, settings)
    with open(MARKER_TEMPLATE) as f:
        marker_template = f.read()
    markers_kml = "\n".join(marker_to_kml(marker, marker_template) for marker in markers)

    with open(KML_TEMPLATE) as f:
        kml_template = f.read()
    kml = kml_template.format(name=settings.destination, placemarks=markers_kml)

    print(f"{len(markers)} markers added for destination: {settings.destination}")

    return kml


def parse_settings() -> Settings:
    """Create settings from command line parameters"""
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
        help="Language of the Wikivoyage article, defaults to 'en'",
    )

    args = parser.parse_args()
    return Settings(
        destination=args.destination, language=args.language, kmz=args.kmz, add=args.add
    )


def save_kml(kml: str, settings: Settings) -> None:
    """Write kml document into file"""
    filename = OUTPUT_FILENAME.format(destination=settings.destination, language=settings.language)

    kml_file_name = f"{filename}.{KML_EXTENSION}"
    with open(kml_file_name, "w") as file:
        file.write(kml)

    if settings.kmz:
        with ZipFile(f"{filename}.{KMZ_EXTENSION}", "w") as zfile:
            zfile.write(kml_file_name)
        os.remove(kml_file_name)


def main() -> None:
    settings = parse_settings()
    kml = create_kml(settings)
    save_kml(kml, settings)


if __name__ == "__main__":
    main()
