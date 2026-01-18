#!/usr/bin/env python3
import sys
from pathlib import Path

if __name__ == "__main__":
    input_file = Path("mock_gshow_output.txt")
    if not input_file.exists():
        sys.exit(1)
    else:
        try:
            with open(input_file, "r") as f:
                for line in f:
                    print(line.rstrip())
        except Exception as e:
            print(f"{e.__class__.__name__}: {e}")
            sys.exit(2)

    sys.exit(0)
