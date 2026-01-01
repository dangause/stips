# Build the metadata config javascript file the frontend needs to be able to talk with the backend.

import argparse
import json
import sys
from pathlib import Path

from lick_archive.metadata import data_dictionary


def get_parser():
    """
    Parse build_metadata_config command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Build the metadata_config.js file used when building the frontend Javascript to allow the frontend to understand the archive's metadata."
    )
    parser.add_argument(
        "output", type=Path, help="Where to output the metadata_config.js file."
    )

    return parser


def main(args):
    result_fields = {
        result["db_name"]: {
            "human_name": result["human_name"],
            "units": data_dictionary.field_units.get(result["db_name"], ""),
        }
        for result in data_dictionary.api_capabilities["result"]
    }
    data_dictionary_wrapper = {"resultFields": result_fields}
    results_js = json.dumps(data_dictionary_wrapper, indent=4)
    with open(args.output, "w") as f:
        f.write(results_js)


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
