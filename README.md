# PROSAIL Sentinel-2 Synthetic Data Generator

This project generates synthetic Sentinel-2 surface-reflectance samples by
running the PROSAIL radiative transfer model at 1 nm resolution and convolving
the resulting spectra with official ESA Sentinel-2A/B/C spectral response
functions (SRFs).

The output is a lookup table (LUT) containing both the input biophysical
parameters (suitable as machine-learning regression targets) and the
corresponding Sentinel-2 band reflectances (suitable as features).

---

## Table of Contents

- [Overview](#overview)
- [Pipeline](#pipeline)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Output Format](#output-format)
- [Project Structure](#project-structure)
- [Method Details](#method-details)
  - [1. Parameter Sampling](#1-parameter-sampling)
  - [2. PROSAIL Simulation](#2-prosail-simulation)
  - [3. Spectral Response Function Convolution](#3-spectral-response-function-convolution)
  - [4. Noise Addition](#4-noise-addition)
  - [5. Streaming CSV Output](#5-streaming-csv-output)
- [Key Design Decisions](#key-design-decisions)
- [Reproducibility](#reproducibility)
- [Memory Safety](#memory-safety)
- [Legacy Script](#legacy-script)

---

## Overview

### What This Project Does

1. **Samples** realistic vegetation biophysical parameters (chlorophyll, leaf
   area index, water content, dry matter, brown pigments, leaf structure,
   leaf angle distribution, hotspot, soil brightness, and observation
   geometry) using Latin Hypercube Sampling combined with correlated latent
   variables.

2. **Simulates** 1-nm resolution hyperspectral reflectance spectra
   (400-2500 nm) by running the PROSAIL model (PROSPECT leaf optical
   properties + SAIL canopy bidirectional reflectance).

3. **Convolves** each spectrum with the official ESA Sentinel-2 SRFs to
   produce band-integrated reflectance values for 10 vegetation-relevant
   Sentinel-2 bands: B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12.

4. **Adds** simulated measurement noise (Gaussian, additive) to each band
   reflectance and clips to the physically meaningful range [0, 1].

5. **Streams** the results to CSV in memory-safe batches, writing to a
   temporary `.part` file first and atomically renaming on completion.

### Why This Matters

- Synthetic LUTs enable training of machine-learning models for biophysical
  parameter retrieval without requiring extensive field campaigns.
- The correlated parameter sampling ensures the synthetic data reflects real
  canopy biophysical relationships (e.g., chlorophyll and carotenoids
  co-vary, senescence increases brown pigments).
- Memory-safe streaming allows generating datasets with hundreds of
  thousands of samples on modest hardware.

---

## Pipeline

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Parameter      │     │  PROSAIL         │     │  SRF             │
│  Sampling       │────▶│  Simulation      │────▶│  Convolution     │
│  (LHS + Latent) │     │  (1-nm spectra)  │     │  (S2 bands)      │
└─────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  CSV Output     │◀────│  Noise Addition  │◀────│  Band            │
│  (streaming)    │     │  + Clipping      │     │  Reflectances    │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

---

## Requirements

- **Python** >= 3.11
- **Dependencies** (automatically installed):
  - `prosail` >= 2.0.5 — radiative transfer model
  - `numpy` >= 1.26 — numerical arrays, RNG, linear algebra
  - `pandas` >= 2.1 — DataFrames, CSV I/O, Excel reading
  - `scipy` — Latin Hypercube Sampling (`qmc`), normal CDF
  - `openpyxl` >= 3.1 — reading `.xlsx` SRF workbook
  - `matplotlib` >= 3.8 — plotting (legacy script only)

---

## Installation

### Using `uv` (recommended)

```powershell
uv sync
```

### Using pip

```powershell
pip install -e .
```

### Manual (without installing the package)

Set `PYTHONPATH` to include the `src` directory:

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m generate_lut --samples 1000 --output output/test.csv
```

---

## Quick Start

### Generate a small LUT (25,000 samples)

```powershell
python -m generate_lut --samples 25000 --output output/lut.csv
```

### Generate a large LUT (600,000 samples, 6 workers)

```powershell
python -m generate_lut --samples 600000 --batch-size 10000 --workers 6 --output output/lut_large.csv
```

### Use Sentinel-2B spectral response functions

```powershell
python -m generate_lut --samples 25000 --platform S2B --output output/lut_s2b.csv
```

### Disable measurement noise

```powershell
python -m generate_lut --samples 25000 --no-noise --output output/lut_clean.csv
```

### Convenience wrapper (hardcoded settings)

Edit the constants at the top of `run_sentinel2_lut.py` and run:

```powershell
python -m run_sentinel2_lut
```

This generates 600,000 samples with 6 workers and a timestamped output
filename.

---

## CLI Reference

All options are available through `python -m generate_lut`:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--samples` | int | 25000 | Total number of LUT rows to generate |
| `--batch-size` | int | 10000 | Rows per processing batch |
| `--workers` | int | 4 | Parallel PROSAIL worker processes |
| `--output` | Path | `output/prosail_sentinel2_lut.csv` | Destination CSV file |
| `--platform` | str | `S2A` | Sentinel-2 platform: `S2A`, `S2B`, or `S2C` |
| `--no-noise` | flag | off | Disable additive reflectance noise |
| `--overwrite` | flag | off | Replace an existing output CSV |

### Validation

- `--samples`, `--batch-size`, and `--workers` must all be >= 1.
- If the output file already exists and `--overwrite` is not given, the
  program exits with `FileExistsError` to prevent accidental data loss.

---

## Output Format

The output CSV contains **PROSAIL parameter columns** followed by **Sentinel-2
band reflectance columns**.

### PROSAIL Parameter Columns (ML targets)

| Column | Description | Range |
|--------|-------------|-------|
| `N` | Leaf structure parameter | 1.2 - 2.3 |
| `Cab` | Chlorophyll content [ug/cm2] | 20 - 80 |
| `Car` | Carotenoid content [ug/cm2] | 4 - 20 |
| `Cbrown` | Brown pigment content | 0.02 - 0.52 |
| `Cw` | Equivalent water thickness [cm] | 0.006 - 0.030 |
| `Cm` | Dry matter content [g/cm2] | 0.004 - 0.020 |
| `LAI` | Leaf Area Index [m2/m2] | 0.1 - 7.0 |
| `LIDFa` | Average leaf inclination angle [deg] | 20 - 70 |
| `Hspot` | Hotspot parameter | 0.02 - 0.37 |
| `TTS` | Solar zenith angle [deg] | 15 - 60 |
| `TTO` | View zenith angle [deg] | 0 - 15 |
| `PSI` | Relative azimuth angle [deg] | 0 - 180 |
| `Psoil` | Soil moisture/brightness parameter | 0 - 1 |
| `Rsoil` | Soil brightness factor | 0.75 - 1.25 |
| `growth_stage` | Canopy growth stage (0=early, 1=mature) | 0 - 1 |

### Sentinel-2 Band Columns (ML features)

| Column | Band | Central Wavelength |
|--------|------|-------------------|
| `B2` | Blue | 490 nm |
| `B3` | Green | 560 nm |
| `B4` | Red | 665 nm |
| `B5` | Red Edge 1 | 705 nm |
| `B6` | Red Edge 2 | 740 nm |
| `B7` | Red Edge 3 | 783 nm |
| `B8` | NIR | 842 nm |
| `B8A` | Narrow NIR | 865 nm |
| `B11` | SWIR 1 | 1610 nm |
| `B12` | SWIR 2 | 2190 nm |

Bands B1 (aerosol), B9 (water vapour), and B10 (cirrus) are excluded as they
are not typically used for vegetation biophysical parameter retrieval.

---

## Project Structure

```
remote sensing/
├── pyproject.toml                              # Project metadata, dependencies
├── README.md                                   # This file
├── src/
│   ├── __init__.py                             # Package init
│   ├── config.py                               # Central dataclass configuration
│   ├── sampler.py                              # Parameter sampling (LHS + correlated latents)
│   ├── srf.py                                  # SRF loading and spectral convolution
│   ├── simulator.py                            # PROSAIL execution + parallel batch processing
│   ├── generate_lut.py                         # Main CLI entry point (streaming LUT generator)
│   ├── generate_prosail_s2.py                  # Legacy standalone script with plotting
│   ├── run_sentinel2_lut.py                    # Convenience wrapper with hardcoded settings
│   └── data/
│       └── sentinel-2-spectral-response-functions-v5.xlsx
└── output/
    ├── streaming_test.csv
    └── parallel_test.csv
```

---

## Method Details

### 1. Parameter Sampling

**File:** `sampler.py`

Parameters are sampled using a two-stage approach that ensures both
space-filling coverage and biological realism.

#### Stage 1: Latin Hypercube Sampling (LHS)

SciPy's `qmc.LatinHypercube` is used to sample 10 independent dimensions
uniformly. LHS guarantees that each dimension is evenly covered across its
full range, avoiding the clustering that occurs with pure random sampling.

The 10 LHS dimensions map to:

1. Growth stage (drives LAI, chlorophyll, carotenoids, water, dry matter,
   brown pigment correlations)
2. LAI base value
3. Brown pigment independent variability
4. Leaf structure parameter (N)
5. Leaf angle (LIDFa)
6. Hotspot parameter
7. Solar zenith angle (TTS)
8. View zenith angle (TTO)
9. Relative azimuth angle (PSI)
10. Soil parameter (Psoil)

#### Stage 2: Correlated Latent Variables

Four latent variables are generated to represent broad vegetation states.
These are NOT direct PROSAIL parameters but are transformed into
biologically meaningful parameters.

**Correlation matrix:**

```
              L1     L2     L3     Senescence
L1          1.00   0.65   0.55       -0.40
L2          0.65   1.00   0.50       -0.35
L3          0.55   0.50   1.00       -0.30
Senescence -0.40  -0.35  -0.30        1.00
```

**Generation process:**

1. Draw independent standard normal variables `z ~ N(0, 1)`.
2. Apply Cholesky decomposition of the correlation matrix: `L = chol(R)`.
3. Correlate: `z_correlated = z @ L.T`.
4. Transform to uniform [0, 1] using the normal CDF: `u = norm.cdf(z_correlated)`.

#### Parameter Transformations

The latent variables and growth stage are combined to produce correlated
PROSAIL parameters:

- **LAI**: `0.1 + 6.9 * (0.35 * LHS + 0.65 * growth_stage)` — denser in the
  mid-range, higher for mature canopies.
- **Cab**: `20 + 60 * (0.35 * L1 + 0.65 * growth_stage)` — increases with
  maturity.
- **Car**: `4 + 16 * (0.65 * L2 + 0.35 * growth_stage)` — correlated with
  chlorophyll but with independent variability.
- **Cw**: `0.006 + 0.024 * (0.65 * L3 + 0.35 * growth_stage)` — related to
  vegetation state.
- **Cm**: `0.004 + 0.016 * (0.5 * L4 + 0.5 * growth_stage)`.
- **Cbrown**: `0.02 + 0.45 * senescence + 0.05 * LHS` — low during healthy
  stage, higher during senescence. Senescence is derived from growth_stage:
  `clip((growth_stage - 0.75) / 0.25, 0, 1)`.
- **N**: `1.2 + 1.1 * LHS` — independent uniform sampling.
- **LIDFa**: `20 + 50 * LHS` — planophile to erectophile range.
- **Hspot**: `0.02 + 0.35 * LHS`.
- **TTS**: `15 + 45 * LHS` (15-60 degrees).
- **TTO**: `15 * LHS` (0-15 degrees, near-nadir).
- **PSI**: `180 * LHS`.
- **Psoil**: Direct LHS value (0-1).
- **Rsoil**: `0.75 + 0.50 * LHS` — correlated with hotspot for physical
  consistency.

---

### 2. PROSAIL Simulation

**File:** `simulator.py`

PROSAIL combines two sub-models:

- **PROSPECT-D**: Leaf optical properties (reflectance and transmittance)
  as a function of leaf biochemical constituents (chlorophyll, carotenoids,
  brown pigments, water, dry matter) and leaf structure (N).
- **SAIL**: Canopy bidirectional reflectance as a function of LAI, leaf angle
  distribution, hotspot, soil reflectance, and sun-sensor geometry.

**Invocation (per sample):**

```python
prosail.run_prosail(
    n=N, cab=Cab, car=Car, cbrown=Cbrown, cw=Cw, cm=Cm,
    lai=LAI, lidfa=LIDFa, hspot=Hspot,
    tts=TTS, tto=TTO, psi=PSI,
    prospect_version="D",
    typelidf=2,       # elliptical leaf angle distribution
    factor="SDR",     # directional reflectance factor
    psoil=Psoil, rsoil=Rsoil
)
```

**Output:** A 2101-element array of surface reflectance values at 1 nm
resolution (400-2500 nm).

**Parallel execution:** The `run_prosail_to_sentinel2_batch()` function
distributes parameter chunks across multiple CPU cores using
`ProcessPoolExecutor`. Each worker process runs PROSAIL and SRF convolution
for its chunk independently, and results are combined via `np.vstack`.

---

### 3. Spectral Response Function Convolution

**File:** `srf.py`

The official ESA Sentinel-2 SRF Excel workbook
(`sentinel-2-spectral-response-functions-v5.xlsx`) stores the relative
spectral response of each detector as a function of wavelength.

**Loading:**

- The workbook contains separate sheets for S2A, S2B, and S2C platforms.
- Column `SR_WL` contains the wavelength axis.
- Columns `{PLATFORM}_SR_AV_{BAND}` contain the response curves.

**Convolution formula:**

For each Sentinel-2 band:

```
             integral[ R(lambda) * SRF(lambda) dlambda ]
R_band = ---------------------------------------------------
                integral[ SRF(lambda) dlambda ]
```

**Implementation:**

1. Interpolate the SRF onto the PROSAIL 1-nm grid using `np.interp`
   (linear interpolation, zero outside the SRF wavelength range).
2. Compute the denominator: `np.trapezoid(response, wavelengths)`.
3. Compute the numerator: `np.trapezoid(spectrum * response, wavelengths)`.
4. Divide: `numerator / denominator`.

This is physically correct band integration — not simply sampling the
reflectance at the band's central wavelength.

**Memory efficiency:** The convolution is performed immediately after each
PROSAIL simulation. The full 2101-band spectrum is never retained in
memory. Only the 10 band-integrated values are stored.

---

### 4. Noise Addition

**File:** `simulator.py`

Additive Gaussian noise simulates measurement uncertainty:

```python
noise = rng.normal(loc=0.0, scale=noise_std, size=reflectance.shape)
noisy = reflectance + noise
noisy = np.clip(noisy, 0.0, 1.0)
```

**Default noise level:** `noise_std = 0.003` (0.3% reflectance).

This is deliberately modest and should eventually be calibrated against the
uncertainty characteristics of the real Sentinel-2 dataset being used.

**Reproducibility:** Each batch uses a seed derived from the base seed:
`random_seed + 500 + batch_index`. This ensures identical output regardless
of batch size or worker count.

---

### 5. Streaming CSV Output

**File:** `generate_lut.py`

The generator processes data in configurable batches (default 10,000 rows)
to avoid memory exhaustion with large sample counts.

**Workflow per batch:**

1. Generate parameters (LHS + correlated latents).
2. Run PROSAIL + SRF convolution (parallel).
3. Add noise (optional).
4. Combine parameters and band reflectances into a DataFrame.
5. Drop rows with NaN values (invalid PROSAIL simulations).
6. Clip band reflectances to [0, 1].
7. Append to the temporary CSV file.

**Atomic output:** Results are written to a `.part` file first. On successful
completion, the `.part` file is atomically renamed to the final output path.
This prevents partial/corrupt files if the process is interrupted.

---

## Key Design Decisions

### Correlated Parameter Sampling

Parameters are NOT independently sampled. The latent variable approach
ensures that chlorophyll, carotenoids, water content, dry matter, and
senescence vary in physically consistent ways. This produces a more
realistic training distribution than independent uniform sampling.

### Memory-Safe Streaming

The full LUT is never held in memory. Each batch is processed independently:
parameters are generated, simulated, convolved, noised, written to disk,
and then discarded. The `_simulate_chunk()` function in `simulator.py`
discards the 2101-band spectrum immediately after convolution, retaining
only the 10 band-integrated values.

### Parallel Execution

`ProcessPoolExecutor` distributes parameter chunks across CPU cores. The
number of workers is configurable via `--workers`. Results are collected in
order and stacked, so output row order is deterministic.

### Reproducibility

All random number generation uses explicit NumPy Generator seeds. Batch
seeds are derived deterministically from the base seed, ensuring identical
output regardless of batch size or worker count.

### Atomic File Output

The `.part` → rename pattern ensures that an interrupted run never leaves a
partial CSV at the final output path. Existing files are protected by
default (require `--overwrite`).

---

## Reproducibility

Running the same command twice with the same seed produces identical output:

```powershell
python -m generate_lut --samples 25000 --output output/lut.csv --overwrite
```

The random seed is fixed at 42 by default (configurable in `Config`).
Batch-dependent seeds are derived as `base_seed + batch_index` for sampling
and `base_seed + 500 + batch_index` for noise.

---

## Memory Safety

| Sample Count | Batch Size | Peak Memory (approx.) |
|-------------|-----------|----------------------|
| 25,000 | 10,000 | ~50 MB |
| 100,000 | 10,000 | ~50 MB |
| 600,000 | 10,000 | ~50 MB |

Peak memory is bounded by the batch size, not the total sample count. The
full dataset is never loaded into memory.

---

## Legacy Script

`generate_prosail_s2.py` is a standalone, self-contained script that does
not use the package modules. It includes:

- Its own SRF loading and parameter sampling (independent uniform, no
  correlated latents).
- Sequential (non-parallel) PROSAIL execution.
- A `plot_example()` function for visualizing a single spectrum with
  Sentinel-2 band reflectances overlaid.

Run it with:

```powershell
python src/generate_prosail_s2.py --samples 10000 --output output.csv --plot preview.png
```

This script is useful as a reference implementation or for smaller runs,
but `generate_lut.py` is recommended for any serious dataset generation.
