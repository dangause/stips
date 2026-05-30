#!/usr/bin/env python
"""Generate Panel 7 QR code pointing at the STIPS repo."""

from pathlib import Path

import qrcode

URL = "https://github.com/danpgause/stips"
OUT = Path(__file__).resolve().parents[1] / "assets" / "panel7_qr.png"


def main() -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=20,
        border=2,
    )
    qr.add_data(URL)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(OUT)
    print(f"wrote {OUT} ({URL})")


if __name__ == "__main__":
    main()
