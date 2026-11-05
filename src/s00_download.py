"""Step 0 - Download the static open datasets (~150 MB). GBIF data is fetched by step 2."""
from __future__ import annotations

import zipfile

import requests

from common import RAW

FILES = {
    # Dr. Duke's Phytochemical and Ethnobotanical Databases, USDA-ARS, CC0 (Ag Data Commons 10.15482/USDA.ADC/1239279)
    "duke/Duke-Source-CSV.zip": "https://ndownloader.figshare.com/files/43363335",
    # World Checklist of Vascular Plants, Royal Botanic Gardens Kew, CC BY 4.0
    "wcvp/wcvp.zip": "https://sftp.kew.org/pub/data-repositories/WCVP/wcvp.zip",
    # TDWG World Geographical Scheme for Recording Plant Distributions, level 3
    "tdwg/level3.geojson": "https://raw.githubusercontent.com/tdwg/wgsrpd/master/geojson/level3.geojson",
}


def main():
    for rel, url in FILES.items():
        dest = RAW / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            print("downloading", url)
            with requests.get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        if dest.suffix == ".zip":
            with zipfile.ZipFile(dest) as z:
                z.extractall(dest.parent)
    print("done")


if __name__ == "__main__":
    main()
