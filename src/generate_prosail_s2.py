import argparse
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import prosail
import matplotlib.pyplot as plt

# Ensure console output does not crash on Windows (cp1252) when printing
# non-ASCII characters. Falls back to replacing unencodable chars.
try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ============================================================
# CONFIGURATION
# ============================================================

N_SAMPLES = 10_000
SRF_FILE = Path("src") / "remote_sensing" / "data" / "sentinel-2-spectral-response-functions-v5.xlsx"
OUTPUT_FILE = "prosail_sentinel2_synthetic.csv"
RANDOM_SEED = 42


# ============================================================
# SENTINEL-2 BANDS
# ============================================================

# Sentinel-2 bands useful for vegetation applications.
#
# B1 is generally not useful for vegetation retrieval,
# so we exclude it.
#
# B10 is a cirrus band and is also excluded.
#
# We retain the standard vegetation-relevant bands.

S2_BANDS = [
    "B2",
    "B3",
    "B4",
    "B5",
    "B6",
    "B7",
    "B8",
    "B8A",
    "B11",
    "B12",
]


# ============================================================
# PROSAIL PARAMETER RANGES
# ============================================================
#
# These are example broad ranges.
#
# IMPORTANT:
# For a serious research dataset, these should be adapted
# to your vegetation/crop type and preferably constrained
# using field measurements or literature.
#
# ============================================================

PARAMETER_RANGES = {

    # Leaf structure
    "N": (1.0, 2.5),

    # Chlorophyll
    "Cab": (20.0, 80.0),

    # Carotenoids
    "Car": (5.0, 20.0),

    # Brown pigment
    "Cbrown": (0.0, 0.5),

    # Leaf water content [cm]
    "Cw": (0.005, 0.030),

    # Leaf dry matter [g/cm²]
    "Cm": (0.003, 0.020),

    # Leaf Area Index
    "LAI": (0.1, 7.0),

    # Average leaf angle [degrees]
    "LIDFa": (20.0, 70.0),

    # Hotspot parameter
    "Hspot": (0.01, 0.5),

    # Solar zenith angle [degrees]
    "TTS": (20.0, 50.0),

    # Sensor/viewing zenith angle [degrees]
    "TTO": (0.0, 20.0),

    # Relative azimuth angle [degrees]
    "PSI": (0.0, 180.0),

    # Soil brightness
    "Rsoil": (0.5, 1.5),

    # Soil moisture / soil mixture parameter
    "Psoil": (0.0, 1.0),
}


# ============================================================
# LOAD SENTINEL-2 SRF
# ============================================================

def load_srf(filename, platform="S2A"):
    """
    Load Sentinel-2 spectral response functions.

    The exact Excel layout can vary between ESA SRF releases.
    This function attempts to identify wavelength and
    Sentinel-2 response columns automatically.
    """

    if not os.path.exists(filename):
        raise FileNotFoundError(
            f"\nSRF file not found:\n{filename}\n\n"
            "Download the official Sentinel-2 SRF Excel file "
            "and put it next to this script."
        )

    platform = platform.upper()
    if platform not in {"S2A", "S2B", "S2C"}:
        raise ValueError("platform must be one of: S2A, S2B, S2C")

    sheet_name = f"Spectral Responses ({platform})"
    print(f"Reading {platform} Sentinel-2 SRFs from sheet: {sheet_name}")
    # The official ESA workbook uses its first row as the column header.
    return pd.read_excel(filename, sheet_name=sheet_name, header=0)


# ============================================================
# GENERATE PROSAIL PARAMETERS
# ============================================================

def generate_parameters(n_samples, rng):

    parameters = {}

    for name, (low, high) in PARAMETER_RANGES.items():

        parameters[name] = rng.uniform(
            low,
            high,
            n_samples
        )

    return pd.DataFrame(parameters)


# ============================================================
# RUN PROSAIL
# ============================================================

def run_prosail_simulation(params):

    spectra = []

    print("\nRunning PROSAIL simulations...")

    for i, row in params.iterrows():

        spectrum = prosail.run_prosail(

            # Leaf parameters
            n=row["N"],
            cab=row["Cab"],
            car=row["Car"],
            cbrown=row["Cbrown"],
            cw=row["Cw"],
            cm=row["Cm"],

            # Canopy
            lai=row["LAI"],
            lidfa=row["LIDFa"],
            hspot=row["Hspot"],

            # Geometry
            tts=row["TTS"],
            tto=row["TTO"],
            psi=row["PSI"],

            # PROSPECT version
            prospect_version="D",

            # Leaf angle distribution
            typelidf=2,

            # Soil
            rsoil=row["Rsoil"],
            psoil=row["Psoil"],

            # Surface directional reflectance
            factor="SDR"
        )

        spectra.append(spectrum)

        if (i + 1) % 1000 == 0:
            print(
                f"  Completed {i + 1:,} / "
                f"{len(params):,}"
            )

    spectra = np.asarray(spectra)

    return spectra


# ============================================================
# LOAD / PREPARE SRF
# ============================================================

def prepare_srf(raw_srf, platform="S2A"):
    """
    Convert the raw ESA SRF spreadsheet into a dictionary:

        {
            "B2":  response array,
            "B3":  response array,
            ...
        }

    This section is intentionally separated from the rest of
    the pipeline because ESA has changed the spreadsheet
    layout between SRF versions.
    """

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # The exact column names/layout depend on the SRF version.
    #
    # We first attempt to find wavelength and band columns.
    # --------------------------------------------------------

    raw = raw_srf.copy()

    raw.columns = [str(column).strip() for column in raw.columns]
    platform = platform.upper()
    wavelength_column = "SR_WL"
    if wavelength_column not in raw.columns:
        raise RuntimeError(
            "The selected SRF worksheet is missing the expected 'SR_WL' column."
        )

    wavelengths = pd.to_numeric(raw[wavelength_column], errors="coerce").to_numpy()

    # --------------------------------------------------------
    # Identify Sentinel-2 band columns
    # --------------------------------------------------------

    srf = {}

    for band in S2_BANDS:

        selected = f"{platform}_SR_AV_{band}"
        if selected not in raw.columns:
            raise RuntimeError(f"Missing SRF column for {band}: {selected}")
        print(f"{band}: using column '{selected}'")

        response = pd.to_numeric(
            raw[selected],
            errors="coerce"
        ).values

        valid = (
            np.isfinite(wavelengths) &
            np.isfinite(response)
        )

        band_wavelengths, band_response = wavelengths[valid], response[valid]
        positive = band_response > 0
        srf[band] = (band_wavelengths[positive], band_response[positive])

    if len(srf) == 0:

        raise RuntimeError(
            "\nNo Sentinel-2 SRFs were detected."
        )

    return srf


# ============================================================
# SRF CONVOLUTION
# ============================================================

def apply_srf(
    prosail_spectrum,
    prosail_wavelengths,
    srf
):
    """
    Convert the 1-nm PROSAIL spectrum into Sentinel-2
    band reflectances.

    Formula:

              ∫ R(lambda) * SRF(lambda) dlambda
    R_band = -----------------------------------
                    ∫ SRF(lambda) dlambda

    This is the important improvement over simply taking
    the reflectance at the band's central wavelength.
    """

    result = {}

    for band, (
        srf_wavelength,
        srf_response
    ) in srf.items():

        # ----------------------------------------------------
        # Only use the wavelength region where the SRF exists.
        # ----------------------------------------------------

        min_wavelength = np.min(srf_wavelength)
        max_wavelength = np.max(srf_wavelength)

        mask = (
            (prosail_wavelengths >= min_wavelength) &
            (prosail_wavelengths <= max_wavelength)
        )

        wavelength = prosail_wavelengths[mask]

        spectrum = prosail_spectrum[mask]

        # ----------------------------------------------------
        # Interpolate SRF onto PROSAIL's 1-nm grid
        # ----------------------------------------------------

        response = np.interp(
            wavelength,
            srf_wavelength,
            srf_response,
            left=0.0,
            right=0.0
        )

        # ----------------------------------------------------
        # Spectral integration
        # ----------------------------------------------------

        denominator = np.trapezoid(response, wavelength)

        if denominator <= 0:

            result[band] = np.nan

            continue

        numerator = np.trapezoid(spectrum * response, wavelength)

        result[band] = (
            numerator / denominator
        )

    return result


# ============================================================
# CONVERT ALL PROSAIL SPECTRA TO SENTINEL-2
# ============================================================

def convert_to_sentinel2(
    spectra,
    wavelengths,
    srf
):

    print("\nConvolving PROSAIL spectra with Sentinel-2 SRFs...")

    results = []

    for i, spectrum in enumerate(spectra):

        result = apply_srf(
            spectrum,
            wavelengths,
            srf
        )

        results.append(result)

        if (i + 1) % 1000 == 0:
            print(
                f"  Converted {i + 1:,} / "
                f"{len(spectra):,}"
            )

    return pd.DataFrame(results)


# ============================================================
# PLOT EXAMPLE
# ============================================================

def plot_example(
    wavelengths,
    spectrum,
    sentinel_data
):

    plt.figure(figsize=(12, 6))

    # PROSAIL hyperspectral spectrum
    plt.plot(
        wavelengths,
        spectrum,
        label="PROSAIL spectrum"
    )

    # Sentinel-2 band centers for visualization only
    band_centers = {
        "B2": 490,
        "B3": 560,
        "B4": 665,
        "B5": 705,
        "B6": 740,
        "B7": 783,
        "B8": 842,
        "B8A": 865,
        "B11": 1610,
        "B12": 2190,
    }

    x = []
    y = []
    labels = []

    for band in sentinel_data.index:

        if band in band_centers:

            x.append(
                band_centers[band]
            )

            y.append(
                sentinel_data[band]
            )

            labels.append(band)

    plt.scatter(
        x,
        y,
        s=60,
        label="Sentinel-2 band reflectance"
    )

    for xi, yi, label in zip(
        x,
        y,
        labels
    ):

        plt.annotate(
            label,
            (xi, yi),
            xytext=(5, 5),
            textcoords="offset points"
        )

    plt.xlabel("Wavelength (nm)")
    plt.ylabel("Surface reflectance")

    plt.title(
        "PROSAIL Spectrum → Sentinel-2 Spectral Sampling"
    )

    plt.grid(True)
    plt.legend()

    plt.tight_layout()

    return plt.gcf()


# ============================================================
# MAIN
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate PROSAIL-based Sentinel-2 surface reflectance samples."
    )
    parser.add_argument("--samples", type=int, default=N_SAMPLES,
                        help=f"number of simulations (default: {N_SAMPLES:,})")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--platform", choices=["S2A", "S2B", "S2C"], default="S2A")
    parser.add_argument("--srf-file", type=Path,
                        default=Path(__file__).parent / SRF_FILE)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name(OUTPUT_FILE))
    parser.add_argument("--plot", type=Path,
                        help="optional path at which to save a PNG preview")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    return args


def main():

    args = parse_args()
    rng = np.random.default_rng(args.seed)

    print("=" * 60)
    print("PROSAIL → SENTINEL-2 SYNTHETIC DATA GENERATOR")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Load Sentinel-2 SRF
    # --------------------------------------------------------

    raw_srf = load_srf(
        args.srf_file, args.platform
    )

    # --------------------------------------------------------
    # 2. Prepare SRF
    # --------------------------------------------------------

    srf = prepare_srf(
        raw_srf, args.platform
    )

    print(
        "\nSentinel-2 bands available:"
    )

    print(
        list(srf.keys())
    )

    # --------------------------------------------------------
    # 3. Generate random PROSAIL parameters
    # --------------------------------------------------------

    print(
        f"\nGenerating {args.samples:,} "
        "PROSAIL parameter sets..."
    )

    params = generate_parameters(
        args.samples, rng
    )

    print("\nParameter dataset:")
    print(
        params.head()
    )

    # --------------------------------------------------------
    # 4. Run PROSAIL
    # --------------------------------------------------------

    spectra = run_prosail_simulation(
        params
    )

    print(
        "\nPROSAIL spectra shape:",
        spectra.shape
    )

    # PROSAIL produces a 1-nm spectrum from 400-2500 nm
    wavelengths = np.arange(
        400,
        2501
    )

    # Safety check
    if spectra.shape[1] != len(wavelengths):

        raise RuntimeError(
            "PROSAIL spectrum length does not match "
            "400-2500 nm wavelength grid."
        )

    # --------------------------------------------------------
    # 5. Convert hyperspectral spectra to Sentinel-2
    # --------------------------------------------------------

    sentinel2_df = convert_to_sentinel2(
        spectra,
        wavelengths,
        srf
    )

    # --------------------------------------------------------
    # 6. Combine PROSAIL parameters + Sentinel-2 bands
    # --------------------------------------------------------

    dataset = pd.concat(
        [
            params.reset_index(drop=True),
            sentinel2_df.reset_index(drop=True)
        ],
        axis=1
    )

    # --------------------------------------------------------
    # 7. Remove invalid simulations
    # --------------------------------------------------------

    before = len(dataset)

    dataset = dataset.dropna()

    after = len(dataset)

    print(
        f"\nRemoved {before - after} "
        "invalid samples."
    )

    # --------------------------------------------------------
    # 8. Clip reflectances to physically sensible range
    # --------------------------------------------------------

    for band in S2_BANDS:

        if band in dataset.columns:

            dataset[band] = dataset[band].clip(
                lower=0,
                upper=1
            )

    # --------------------------------------------------------
    # 9. Save dataset
    # --------------------------------------------------------

    args.output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.output, index=False)

    print(
        "\nDataset saved to:"
    )

    print(
        os.path.abspath(
            args.output
        )
    )

    # --------------------------------------------------------
    # 10. Display dataset
    # --------------------------------------------------------

    print(
        "\nDataset shape:"
    )

    print(
        dataset.shape
    )

    print(
        "\nFirst five rows:"
    )

    print(
        dataset.head()
    )

    # --------------------------------------------------------
    # 11. Plot one example
    # --------------------------------------------------------

    if args.plot:
        args.plot.parent.mkdir(parents=True, exist_ok=True)
        figure = plot_example(wavelengths, spectra[0], sentinel2_df.iloc[0])
        figure.savefig(args.plot, dpi=160)
        plt.close(figure)
        print(f"Preview plot saved to: {args.plot.resolve()}")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
