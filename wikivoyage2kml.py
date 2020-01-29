#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Wikivoyage2KML: Script to generate kml/kmz files for maps.me from Wikivoyage articles"""

import argparse
import datetime
import html
import os
import sys
import time
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

OUTPUT_KML = '{dest} ({lang}) - Wikivoyage2KML.kml'
OUTPUT_KMZ = '{dest} ({lang}) - Wikivoyage2KML.kmz'
WIKI_URL = 'https://{lang}.wikivoyage.org/w/api.php'

MARKER_TYPES = {'do': {'color': 'teal', 'icon': 'Entertainment'},
                'go': {'color': 'brown', 'icon': 'Transport'},
                'buy': {'color': 'pink', 'icon': 'Shop'},
                'eat': {'color': 'red', 'icon': 'Food'},
                'see': {'color': 'green', 'icon': 'Sights'},
                'drink': {'color': 'yellow', 'icon': 'Bar'},
                'sleep': {'color': 'blue', 'icon': 'Hotel'},
                'default': {'color': 'gray', 'icon': 'None'}}


def get_ts():
    """Get current timestamp in %Y-%m-%dT%H:%M:%SZ format

    :return:
    :rtype: str
    """
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")


def get_wikicode(dest, lang):
    """Get the wikicode of a wikivoyage article for the given destination

    :param dest: destination
    :type dest: str
    :param lang: language on ISO 639-1 format
    :type lang: str
    :return:
    :rtype: str
    """
    try:
        response = requests.get(WIKI_URL.format(lang=lang),
                                params={'action': 'query',
                                        'format': 'json',
                                        'titles': dest,
                                        'prop': 'revisions',
                                        'rvprop': 'content'}).json()
    except ConnectionError:
        sys.exit("Error trying to get page '{}' in https://{}.wikivoyage.org/".format(dest, lang))

    page = next(iter(response['query']['pages'].values()))
    if 'missing' in page:
        sys.exit("Page for '{}' does not exisit in https://{}.wikivoyage.org/".format(dest, lang))
    wikicode = page['revisions'][0]['*']

    return wikicode


def marker_to_kml(marker):
    """Create KML code for a marker

    :param marker:
    :type: dict[str, str]
    :return:
    :rtype: str
    """
    # HTML functions
    a = lambda h, t: "<a href='{}'>{}</a>".format(h, t)
    b = lambda t: "<b>{}</b>".format(t)

    contents = []
    with open('templates/Placemark.kml') as f:
        tpl = f.read()

    # TODO: Fix images to get proper links
    # if 'image' in marker:
    #     contents.append("<img src='{img}'></img>".format(img=marker['image']))
    if 'added_location' in marker:
        contents.append(b("WARNING: ") + "Location has been added automatically, marker may not be correct")
    if 'url' in marker:
        contents.append(b("URL: ") + a(marker['url'], marker['url']))
    if 'phone' in marker:
        contents.append(b("Phone number: ") + a("tel:" + marker['phone'], marker['phone']))
    if 'email' in marker:
        contents.append(b("Email: ") + a("mailto:" + marker['email'], marker['email']))
    if 'address' in marker:
        contents.append(b("Address: ") + marker['address'])
    if 'directions' in marker:
        contents.append(b("Directions: ") + marker['directions'])
    if 'hours' in marker:
        contents.append(b("Opening hours: ") + marker['hours'])
    if 'content' in marker:
        contents.append(b("Place description:"))
        contents.append(marker['content'])

    kml = tpl.format(name=marker['name'],
                     description="<br/>".join(contents),
                     timestamp=get_ts(),
                     color=MARKER_TYPES[marker['type']]['color'],
                     coordinates=marker['long'] + ", " + marker['lat'],
                     icon=MARKER_TYPES[marker['type']]['icon'])

    return kml


def valid_coordinates(marker):
    """Checks wether coordinates are valid: a number between 90 and -90 for latitude and -180 and 180 for longitude

    :param marker:
    :type marker: dict[str, str]
    :return:
    :rtype: bool
    """
    try:
        if abs(float(marker['long'])) > 180 or abs(float(marker['lat'])) > 90:
            raise ValueError
    except (KeyError, ValueError):
        return False

    return True


def extract_markers(wikicode, dest, add_locations=False):
    """Extracts the markers for a given wikicode text

    :param wikicode: wikicode text
    :type wikicode: str
    :param dest: destination name
    :type dest: str destination city on wikivoyage
    :param add_locations: try to get locations from Nominatim for markers that don't have them
    :type add_locations: bool
    :return: list of markers
    :rtype: list[dict[str, str]]
    """
    parsed = wtp.parse(wikicode)
    markers = []

    for t in parsed.templates:
        marker = {a.name.strip(): html.escape(a.value.strip()) for a in t.arguments if a.value.strip()}

        mtype = t.name.strip()
        if mtype in ['marker', 'listing']:
            mtype = marker.get('type', 'default')
        if mtype not in list(MARKER_TYPES):
            mtype = 'default'
        marker['type'] = mtype

        if 'name' not in marker:  # Discard invalid markers
            continue

        if valid_coordinates(marker):
            markers.append(marker)
        elif add_locations:
            marker = add_location(marker, dest)
            if valid_coordinates(marker):
                markers.append(marker)

    return markers


def add_location(marker, dest):
    """Try to add GPS coordinates to a marker in the given destination from Nominatim

    :param marker: dictionary containing information of a pin on the map
    :type marker: dict[str, str]
    :param dest: destination to help with the Nominatim query
    :type dest: str
    :return: the marker with the coordinates updated if any was found
    :rtype marker: dict[str, str]
    """
    geolocator = Nominatim(user_agent="wikivoyage2klm")
    location = None

    if marker.get('address', None):
        time.sleep(1)  # Comply with Nominatim usage policy of one request per second

        try:
            location = geolocator.geocode(query={'street': marker['address'], 'city': dest})
        except GeocoderServiceError:
            print("Marker for '{}' not added because Nominatim error".format(marker['name']))
            time.sleep(10)  # Too many requests to Nominatim, taking a rest

        if location:  # Location found
            marker['long'] = str(location.longitude)
            marker['lat'] = str(location.latitude)
            marker['added_location'] = 'yes'
            print("Marker for '{}' added using automatic location".format(marker['name']))
        else:
            print("Marker for '{}' could not be found on Nominatim".format(marker['name']))

    else:
        print("Marker for '{}' Not added because address is missing".format(marker['name']))

    return marker


def create_kml(dest, add_locations, lang):
    """Creates the kml document for the given destination

    :param dest: wikivoyage destination
    :type dest: str
    :param add_locations: try to get locations from Nominatim for markers that don't have them
    :type add_locations: bool
    :param lang: language for the wikivoyage article
    :type lang: str
    :return: string containing the kml document
    :rtype: str
    """
    wikicode = get_wikicode(dest, lang)
    markers = extract_markers(wikicode, dest, add_locations)
    markers_kml = '\n'.join(marker_to_kml(m) for m in markers)

    with open('templates/Wikivoyage2KML.kml') as f:
        tpl = f.read()
    kml = tpl.format(name=dest, timestamp=get_ts(), placemarks=markers_kml)

    print("{} markers added for destination: {}".format(len(markers), dest))

    return kml


def main():
    # Args parsing
    parser = argparse.ArgumentParser(description='Create KML files for maps.me from Wikivoyage articles')
    parser.add_argument('destination', help='Destination name')
    parser.add_argument('-z', '--kmz', action="store_true", default=False, help='Save output to KMZ format')
    parser.add_argument('-a', '--add', action="store_true", default=False, help='Add missing locations')
    parser.add_argument('-l', '--language', default='en', help='Language of the Wikivoyage article')
    args = parser.parse_args()

    kml = create_kml(args.destination, args.add, args.language)

    # Output to KML
    kml_file = OUTPUT_KML.format(dest=args.destination, lang=args.language)
    with open(kml_file, 'w') as f:
        f.write(kml)

    # Output to KMZ
    if args.kmz:
        with ZipFile(OUTPUT_KMZ.format(dest=args.destination, lang=args.language), 'w') as zfile:
            zfile.write(kml_file)
        os.remove(kml_file)


if __name__ == '__main__':
    main()
