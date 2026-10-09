# Calibration

`stips calibs <night>` builds biases and flats as for any instrument (see
{doc}`../nickel/calibration`). Y4KCam's four amplifiers need more instrument
signature removal, which the profile's `isr_overrides` switch on for both the
calibration builds and science, so they are corrected consistently.

## Amplifiers and overscan

Each quadrant is read by its own amplifier toward the centre of the chip,
with overscan strips along the inner edges. STIPS subtracts both the serial
and the parallel overscan. The parallel pass removes a bias step of about
2.5 ADU between amplifier rows, which serial overscan alone leaves as a
visible seam. Each amplifier has its own gain, measured by photon transfer on
34 pairs of dome flats.

## Saturation

Saturated star cores are masked at 65,535 ADU, and the mask is grown by 8
pixels and interpolated over, so that bleed trails are excluded too. Without
the growth, difference imaging detected bleed trails as sources: about 40% of
the spurious detections on the dense SA98 standard field.

## Crosstalk

A bright source in one quadrant leaves a faint copy in the others. The
profile carries a crosstalk matrix measured with `stips measure-crosstalk` on
the E2 standard field (13 November 2011, binned 2 × 2), with coefficients of
0.1–0.4%, largest between adjacent quadrants. STIPS certifies it and enables
crosstalk correction in ISR. The coefficients are indicative; re-measuring on
a brighter, denser field would tighten them. See {doc}`../../crosstalk`.

## Defects and amplifier A01

Curated defect masks ship in `instruments/ctio1m/obs_ctio1m_data/`:

| File | Valid from | Masks |
|---|---|---|
| `19700101T000000.ecsv` | Always | Nothing |
| `20100101T000000.ecsv` | 1 January 2010 | All of amplifier A01, the lower-right quadrant |

Amplifier A01 recorded no light during the January 2010 run that includes the
SA98 standard field, although it worked in 2006, so about three quarters of
the detector is usable for that run. A curated mask stays valid until a newer
file replaces it, so A01 is also masked for any later data. If your post-2010
data show A01 working, add a newer empty mask file dated after the faulty
run; the package README describes the format.
