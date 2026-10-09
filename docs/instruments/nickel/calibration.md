# Calibration

`stips calibs <night>` builds a night's calibrations with Rubin's calibration
products pipeline (`cp_pipe`). Each night needs biases and, for every band you
process, flats.

| Step | What happens |
|---|---|
| Ingest | The night's raws are screened (see {doc}`data`) and ingested |
| Bias | Combined from the night's bias frames, overscan-corrected |
| Flat | Combined per filter from the night's flats, bias-subtracted |
| Certify | Bias and flats are certified into `Nickel/calib/<night>` and chained into `Nickel/calib/current` |

Instrument signature removal subtracts the serial overscan (the 32 columns to
the right of the image), the bias, and the flat, and masks the curated
defects. The single-amplifier camera has no crosstalk correction, and like
every STIPS instrument it runs without a linearity correction.

## Defect mask

STIPS ships one curated defect mask, valid for all dates, in the
`obs_nickel_data` package
(`instruments/nickel/obs_nickel_data/Nickel/defects/ccd0/`). `stips calibs`
writes it, with the camera geometry, into `Nickel/calib/curated`.

The mask was built from a median flat by `stips-defects-build`, which flags
pixels more than 10% above or below a smoothed copy of the flat and keeps
connected regions of at least 8 pixels. To rebuild it from your own flats,
follow the recipe in
[`instruments/nickel/defects/README.md`](https://github.com/dangause/stips/blob/main/instruments/nickel/defects/README.md).

## Problems with a night's calibrations

- **No flats in a band.** That band cannot be processed that night. STIPS
  processes the broadband filters (B, V, R, I) as one group and each other
  filter on its own, so a missing narrow-band or Sloan flat does not affect
  the broadband reduction.
- **A failed bias combine** fails the night's calibrations. One known cause,
  a test readout of the wrong size, is removed by the raw screen; for others,
  read `logs/<run id>/calibs/<night>.log`.
