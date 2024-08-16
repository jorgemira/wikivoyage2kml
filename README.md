# wikivoyage2kml

Script to create a KML/KMZ files with markers for a city from Wikivoyage articles

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for 
development and testing purposes. 

## Installation

Get source code, update the necessary libs using poetry and you're set!

```bash
git clone https://github.com/jorgemira/wikivoyage2kml
cd wikivoyage2kml
poetry install
poetry shell
```

## Usage

```bash
python wikivoyage2kml.py -h
    usage: wikivoyage2kml.py [-h] [-z] [-a] [-l LANGUAGE] destination

    Create KML files for maps.me from Wikivoyage articles
    
    positional arguments:
      destination           Destination name
    
    optional arguments:
      -h, --help            show this help message and exit
      -z, --kmz             Save output to KMZ format
      -a, --add             Add missing locations
      -l LANGUAGE, --language LANGUAGE
                            Language code of the Wikivoyage article, defaults to 'en'
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would 
like to change.

Please make sure to update tests as appropriate.

## License
[Apache 2.0](https://choosealicense.com/licenses/apache-2.0/)