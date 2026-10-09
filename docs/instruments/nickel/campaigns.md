# Example campaigns

These configs, in
[`scripts/config/`](https://github.com/dangause/stips/tree/main/scripts/config),
are real Nickel campaigns. Copy the closest one and change the `env:` paths,
target, and nights.

| Config | Target | Shows |
|---|---|---|
| `2023ixf/pipeline_ps1_template.yaml` | SN 2023ixf, Type II in M101 | PS1 templates (`auto`), r, i, r′, i′, 21 nights, Gaia/PS1 calibration |
| `2023ixf/pipeline_nickel_template.yaml` | SN 2023ixf | Coadd templates, B, V, R, I; its template nights still hold some SN light |
| `2020wnt/pipeline_ps1_template.yaml` | SN 2020wnt, superluminous | PS1 templates |
| `2020wnt/pipeline_nickel_template.yaml` | SN 2020wnt | Coadd templates, V, R, I |
| `cy_aqr/`, `dy_peg/`, `ac_and/` | Pulsating variables | `pipeline_type: variable` with a period search |
| `example_variable_star/` | Annotated template | A starting point for variables |
| `hd189733/pipeline_transit.yaml` | HD 189733 b | `pipeline_type: transit`, no template, B band at 4 s cadence |
| `example_exoplanet/` | Annotated template | A starting point for transits |
| `landolt_validation/` | Landolt standards | Calibration and science only, for checking photometry |
| `extended_objects/` | Several fields, eight filters | Bulk calibration and science, no templates |

The two SN 2023ixf configs reduce the same supernova with PS1 and with coadd
templates, so they are a useful pair for comparing the two.
