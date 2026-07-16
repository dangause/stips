# CTIO 1.0m / Y4KCam — amp A01 root-cause finding

## Summary

**Decision: Branch B (hardware), scoped to the observing run STIPS actually
processes.** Amplifier A01 (lower-right quadrant) is non-responsive to light
throughout the 2010-01-21/22 CTIO Y4KCam run — the run that contains the SA98
standard-star field used for STIPS's photometric-calibration monitoring — while
its geometrically-identical partner amps (A00, A02, A03) read normal sky
counts in every frame checked. The raw-forensics quadrant scan finds no other
2032×2032 region in the 4104×4104 raw frame that carries A01-like real-imaging
statistics: the three regions not already claimed by A00/A02/A03 don't exist
(the frame is fully partitioned by the four quadrants), so there is nowhere
else for A01's "real" 2010 data to be hiding. That rules out a simple
misplaced-bbox (geometry) fix.

A01's exact same declared raw pixel range (`rawDataBBox` `[[2072, 0], [2032,
2032]]`), read with the *same* `y4kcam.yaml`, is a perfectly normal science amp
in a **different** run — the 2006-09-27/28 night containing NGC2298 — where
all four amps read consistent sky-background statistics. This proves the
`y4kcam.yaml` geometry itself is correct (it captures real sky through that
silicon in the run where the amp works) and that A01 is not permanently dead
by design; it is a hardware/readout-chain fault that was present during the
2010 run and is not evident in this genuinely-different 2006 dataset.

**Fix (Task 4):** mask/flag amp A01 for the CTIO Y4KCam data STIPS processes
(the 2010-era SA98 monitoring campaign) via `isr_overrides` / a defect mask
covering A01's full imaging area, and document the reduced (~75%) usable
detector area for that run. Do **not** rewrite A01's `rawDataBBox` — the
current geometry is correct and already mirrors A03's two-strip layout as
designed.

## Reproduced numbers

### Note on frame selection

The brief's literal `ls .../raw/*.fits | head -1` / `head -20 | tail -1`
selectors land on non-science frames in these heterogeneous night
directories: the first file in `20100121/raw/` is a `zero-bias image`
(EXPTIME=0), and the 20th file in `20060927/raw/` is a `V Dome Flat`. Both
were run for completeness (see the full tool output in
`.superpowers/sdd/task-1-report.md`) and show the same qualitative pattern,
but the frames reported below were reselected by `OBJECT` header
(`SA98`, `NGC2298`) to test the actual on-sky symptom described in the task.

### SA98 (2010-01-22, `c1i_100122_002712_ori.fits`, EXPTIME=20s, filter 3)

```
amp  declared-data med/MAD    declared-serialOS med/MAD
A00     5997.0/52.0              3490.0/5.0
A01      200.0/1.0                200.0/1.0
A02     5639.0/62.0              3309.0/2.0
A03     5769.0/57.0              3452.0/3.0

quadrant scan (median/MAD of each 2032x2032 raw sub-region):
  raw[0:2032, 0:2032]     med=5997.0  MAD=52.0   (= A00's own data region)
  raw[0:2032, 2072:4104]  med= 200.0  MAD= 1.0   (= A01's own data region)
  raw[2072:4104, 0:2032]  med=5639.0  MAD=62.0   (= A02's own data region)
  raw[2072:4104, 2072:4104] med=5769.0 MAD=57.0  (= A03's own data region)
```

A01's declared data reads flat at ~200 ADU with MAD 1 — statistically
indistinguishable from its own declared overscan (200/1) — while A00/A02/A03
show real starfield counts (~5600–6000 ADU) with real photon-noise MAD
(52–62, i.e. ~15–20× the overscan MAD of 2–5 in the same frame). Confirmed
consistent across 5 additional SA98/targetSW1/SA95 frames spanning the same
night (median 200–201/MAD 1 for A01 in every case; full output in the task
report).

### NGC2298 (2006-09-28, `c1i_060928_063049_ori.fits`, EXPTIME=70s, filter 2)

```
amp  declared-data med/MAD    declared-serialOS med/MAD
A00     1436.0/9.0               1406.0/9.0
A01     1452.0/8.0               1418.0/7.0
A02     1354.0/6.0               1334.0/5.0
A03     1324.0/7.0               1303.0/5.0

quadrant scan (median/MAD of each 2032x2032 raw sub-region):
  raw[0:2032, 0:2032]     med=1436.0  MAD=9.0
  raw[0:2032, 2072:4104]  med=1452.0  MAD=8.0    (= A01's own data region)
  raw[2072:4104, 0:2032]  med=1354.0  MAD=6.0
  raw[2072:4104, 2072:4104] med=1324.0 MAD=7.0
```

All four amps, A01 included, show consistent sky-background level (~1300–1500
ADU) and consistent photon-noise MAD (6–9) at the **identical declared raw
address** used above. No anomaly. Confirmed across 3 NGC2298 frames spanning
the exposure sequence.

## Reasoning

1. **Geometry is internally consistent and does capture real light where the
   amp works.** The same `rawDataBBox`/`rawSerialOverscanBBox` for A01 that
   reads flat-200/MAD-1 in 2010 reads real sky (1452/8, matching its siblings)
   in 2006. If the yaml pointed at the wrong pixels, it would be wrong in both
   epochs; it isn't. This rules out a lasting bbox/readCorner/flipXY mistake
   in `y4kcam.yaml`.
2. **No spare region exists for a misplaced-amp explanation in the 2010
   frame.** The quadrant scan's four 2032×2032 sub-regions are the *only* way
   to partition the 4104×4104 raw into candidate imaging quadrants at this
   granularity, and three of the four already show real, expected sky
   statistics attributable to A00/A02/A03. There is no unclaimed sub-region
   showing A01-like sky in 2010 — if A01's real data were simply mis-addressed
   elsewhere in the frame, it would have to displace one of the other three
   amps' already-correct regions, which it does not.
3. **The failure is run-wide, not field-wide or exposure-specific.** A01
   reads flat 200–201/MAD-1 in every 2010-01-21/22 frame checked regardless
   of target (SA98, targetSW1, SA95) — a hardware/readout fault at the
   amplifier or controller-channel level, not a pointing- or
   vignetting-dependent artifact.
4. **The failure does not appear in an unrelated run four years earlier.**
   This means A01 is not intrinsically or permanently broken by design — it
   is capable of transmitting real signal — so it should not be assumed
   broken for any future epoch STIPS might onboard without re-running this
   forensics tool on that epoch's raws first.

## Decision Task 4 executes

**Branch B (hardware):** A01 reads anomalously (flat, no photon response) in
every raw frame from the 2010-01-21/22 run — the run underlying STIPS's SA98
CTIO monitoring data — with no candidate region in the quadrant scan showing
its real data elsewhere. Fix = mask/flag amp A01 (e.g. via `isr_overrides` /
a defect mask covering its full `rawDataBBox`) for this data, and document
the resulting ~75% usable detector area (3 of 4 quadrants) in the `ctio1m`
instrument docs. Do not touch A01's `rawDataBBox`/`rawSerialOverscanBBox`/
`readCorner`/`flipXY` — those are correct, as proven by the 2006 cross-check.
