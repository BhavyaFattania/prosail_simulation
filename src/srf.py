# ============================================================
# srf.py
# ============================================================

import numpy as np
import pandas as pd
from pathlib import Path


# ============================================================
# Load SRF
# ============================================================

def load_srf_excel(
    filename,
    bands,
    platform="S2A",
):

    """
    Attempts to identify Sentinel-2 SRF data from the official
    ESA spreadsheet.

    Returns:

        {
            "B2": (wavelength, response),
            "B3": (...),
            ...
        }
    """

    filename = Path(filename)
    if not filename.is_file():
        raise FileNotFoundError(f"Sentinel-2 SRF workbook not found: {filename}")

    platform = platform.upper()
    if platform not in {"S2A", "S2B", "S2C"}:
        raise ValueError("platform must be one of S2A, S2B, or S2C")

    sheet = f"Spectral Responses ({platform})"
    print(f"\nUsing SRF sheet: {sheet}")
    # The official ESA workbook stores names (including SR_WL) in row 1.
    candidate = pd.read_excel(filename, sheet_name=sheet, header=0)
    candidate.columns = [str(column).strip() for column in candidate.columns]

    wavelength_col = "SR_WL"
    if wavelength_col not in candidate.columns:
        raise RuntimeError(f"Missing '{wavelength_col}' in SRF sheet: {sheet}")

    wavelengths = pd.to_numeric(candidate[wavelength_col], errors="coerce").to_numpy()

    # --------------------------------------------------------
    # Find each band
    # --------------------------------------------------------

    srf = {}

    for band in bands:

        selected = f"{platform}_SR_AV_{band}"
        if selected not in candidate.columns:
            raise RuntimeError(f"Missing SRF column for {band}: {selected}")

        response = pd.to_numeric(
            candidate[selected],
            errors="coerce"
        ).values

        valid = (
            np.isfinite(wavelengths)
            &
            np.isfinite(response)
        )

        srf_wavelengths = wavelengths[valid]
        srf_response = response[valid]
        positive = srf_response > 0
        srf[band] = (srf_wavelengths[positive], srf_response[positive])

        print(
            f"{band}: {selected}"
        )

    if len(srf) == 0:

        raise RuntimeError(
            "No Sentinel-2 SRFs were found."
        )

    return srf


# ============================================================
# Convolve one PROSAIL spectrum
# ============================================================

def convolve_spectrum(
    spectrum,
    wavelengths,
    srf
):

    output = {}

    for band, (
        srf_wavelength,
        srf_response
    ) in srf.items():

        # ----------------------------------------------------
        # Interpolate SRF to PROSAIL grid
        # ----------------------------------------------------

        response = np.interp(
            wavelengths,
            srf_wavelength,
            srf_response,
            left=0.0,
            right=0.0
        )

        # ----------------------------------------------------
        # Normalize
        # ----------------------------------------------------

        denominator = np.trapezoid(
            response,
            wavelengths
        )

        if denominator <= 0:

            output[band] = np.nan

            continue

        # ----------------------------------------------------
        # Spectral integration
        # ----------------------------------------------------

        numerator = np.trapezoid(
            spectrum * response,
            wavelengths
        )

        output[band] = (
            numerator /
            denominator
        )

    return output


# ============================================================
# Batch convolution
# ============================================================

def convolve_all(
    spectra,
    wavelengths,
    srf
):

    results = []

    for i, spectrum in enumerate(
        spectra
    ):

        result = convolve_spectrum(
            spectrum,
            wavelengths,
            srf
        )

        results.append(
            result
        )

        if (i + 1) % 10_000 == 0:

            print(
                f"SRF convolution: "
                f"{i + 1:,}"
            )

    return pd.DataFrame(
        results
    )
