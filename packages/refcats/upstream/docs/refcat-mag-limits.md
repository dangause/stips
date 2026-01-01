# Reference Catalog Magnitude Limits (Gaia DR3 & PS1 DR2)

## Purpose
To keep reference-catalog downloads fast and the resulting calibrators high quality for Nickel imaging, we apply simple magnitude windows when querying Gaia DR3 and Pan-STARRS1 DR2. These limits remove stars that are (a) too bright to be reliable in typical Nickel exposures (saturated/non-linear) and (b) so faint that they add bandwidth/CPU cost but little calibration value.

The Nickel field used here is a cone of radius **0.09 deg** (≈ 5.4′). The cone area is π × (0.09)² ≈ **0.0254 deg²**, which is small enough that including unnecessary stars multiplies request/merge time without improving solutions.

## Recommended Defaults

- **Gaia DR3 (G band):** **7.0 ≤ G ≤ 20.5**
- **PS1 DR2 (Mean PSF mags):** **12.0 ≤ r ≤ 20.5**
  *(If calibrating in I/clear, `i` as the anchor band is also reasonable.)*

These values are exposed as CLI flags in the fetchers and may be adjusted per dataset.

## Rationale

### Bright-end cuts

**Goal:** avoid saturated or strongly non-linear stars in Nickel images.

- On a 1-m class telescope, stars brighter than roughly **r ≲ 11–13** will saturate quickly in common exposure times (tens to a few hundred seconds), depending on seeing, focus, full-well, and filter. A bright cut of **r ≥ 12** is a conservative default that excludes the most problematic sources while leaving ample calibrators in a 5.4′ cone.
- Gaia measures very bright stars well, but those same sources are the ones most likely to be saturated in Nickel data. A bright cut of **G ≥ 7** removes the worst cases and keeps the reference list representative of what will be usable on the frames.

**If you know your empirical saturation magnitude**, set the bright cut to about **0.5–1.0 mag fainter** than that value.

### Faint-end cuts

**Goals:** keep calibrators with adequate S/N and reduce network/CPU cost.

- Below ~20.5–21 mag, PSF S/N in short/medium Nickel exposures often becomes marginal, and centroiding quality drops relative to brighter stars. Those rows inflate query size and merge time but rarely improve the fit.
- Capping the faint end at **20.5** significantly reduces the number of returned sources per cone while retaining plenty of tie stars (typically tens at high Galactic latitude, more near the plane).

If a field is star-poor (high |b|, short exposures), raising the faint limit to **21.0** is reasonable. If a field is very crowded or you are bandwidth-constrained, **20.0** can be used.

## Implementation Details

### Gaia (astroquery.gaia)
- **Server-side filtering.** The ADQL includes:
  - `phot_g_mean_mag BETWEEN [g_min, g_max]`
  - sanity checks on flux and `*_flux_over_error > 0` to avoid division warnings on convert.
- Flags:
  - `--g-min` (default **7.0**)
  - `--g-max` (default **20.5**)
- Applies in both code paths:
  - TAP upload (join to uploaded cone centers)
  - No-upload fallback (OR-of-`CIRCLE` predicates)

**Example:**

```bash
python scripts/gaia_fetch.py \
  --butler /path/to/repo --instrument Nickel \
  --registry-where "visit.observation_reason='science'" \
  --radius-deg 0.09 \
  --g-min 7.0 --g-max 20.5 \
  --outdir ./data/gaia_dr3_cones_batched \
  --merged-parquet ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.parquet \
  --merged-csv ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv
````

### PS1 (astroquery.mast)

* **Client-side filtering.** `astroquery.mast.Catalogs.query_region` does not expose an SQL WHERE for PS1; we therefore filter the returned table locally.
* Flags:

  * `--mag-band {g,r,i,z,y}` (default **r**)
  * `--mag-min` (default **12.0**)
  * `--mag-max` (default **20.5**)
* If the selected band column is not present for a particular row, the row is dropped (it would not be used in calibration anyway).

**Example:**

```bash
python scripts/ps1_fetch_mast.py \
  --butler /path/to/repo --instrument Nickel \
  --registry-where "visit.observation_reason='science'" \
  --radius-arcmin 5.4 \
  --mag-band r --mag-min 12.0 --mag-max 20.5 \
  --outdir ./data/ps1_cones_batched \
  --merged-parquet ./data/ps1_all_cones/merged_ps1_cones.parquet \
  --merged-csv ./data/ps1_all_cones/merged_ps1_cones.csv
```

*(Alternative: the CasJobs-based PS1 fetcher supports a server-side WHERE on `m.<band>MeanPSFMag` if you need higher throughput.)*

## When to Adjust

* **Exposure time / filter**

  * Longer exposures → increase bright cut (e.g., `r_min` 13–14).
  * Short exposures → you can relax bright cut (e.g., `r_min` 10–11).
* **Desired depth**

  * Need more tie stars → raise faint cut (e.g., `r_max` 21.0).
  * Bandwidth constrained → lower faint cut (e.g., `20.0`).
* **Field density**

  * Crowded fields (low |b|): consider a tighter faint cut to reduce row counts.
  * Sparse fields (high |b|): allow slightly fainter if needed.

## Optional Quality Filters

These are not enabled by default but can be helpful for very clean astrometry:

* **Gaia**: `ruwe < 1.4`, `visibility_periods_used ≥ 8` (removes many problematic solutions and unresolved binaries).
* **PS1 (CasJobs path)**: `nDetections ≥ 2`, or filters on `qualityFlag/objInfoFlag`.

Each additional cut reduces row count further and may improve fit robustness, at the cost of fewer tie stars.

## Validation

* **Sanity counts:** per cone, expect at least a few dozen calibrators at high |b|; near the plane you may have hundreds.
* **Convert step:** no missing columns; flux error computation should not emit warnings after the `*_flux_over_error > 0` check.
* **Downstream:** astrometric/photometric fit should converge without relying on extremely bright or extremely faint sources.

---

**Summary:** The default windows (**Gaia: 7–20.5 G**, **PS1: 12–20.5 in r**) are conservative, fast, and effective for Nickel. They can be tightened or relaxed via CLI flags based on exposure depth, filter, and field density, with optional quality cuts when cleaner calibrators are preferred.
