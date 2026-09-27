# ============================================================
# config.py
# ============================================================

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:

    # --------------------------------------------------------
    # Dataset
    # --------------------------------------------------------

    # A practical default for a laptop/desktop. Increase explicitly only after
    # checking the memory estimate in the README.
    n_samples: int = 25_000

    random_seed: int = 42

    output_file: Path = Path("output/prosail_sentinel2_lut.csv")

    # --------------------------------------------------------
    # Sentinel-2 SRF
    # --------------------------------------------------------

    srf_file: Path = (
        Path(__file__).parent / "data" /
        "sentinel-2-spectral-response-functions-v5.xlsx"
    )

    platform: str = "S2A"

    # Sentinel-2 vegetation-relevant bands.
    #
    # B1: generally excluded from vegetation retrieval
    # B9: water-vapour band
    # B10: cirrus
    #
    # These can be added later if your application needs them.

    sentinel_bands = (
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
    )

    # --------------------------------------------------------
    # PROSAIL wavelength grid
    # --------------------------------------------------------

    wavelength_start: int = 400

    wavelength_end: int = 2500

    wavelength_step: int = 1

    # --------------------------------------------------------
    # Noise
    # --------------------------------------------------------

    add_noise: bool = True

    # Standard deviation of additive reflectance noise.
    #
    # This is deliberately modest. It should eventually be
    # replaced/calibrated using the uncertainty characteristics
    # of the real Sentinel-2 dataset being used.

    noise_std: float = 0.003

    # --------------------------------------------------------
    # Geometry
    # --------------------------------------------------------

    # Approximate range for solar zenith angle.
    solar_zenith_min: float = 15.0
    solar_zenith_max: float = 60.0

    # Sentinel-2 observations are usually close to nadir,
    # but not exactly nadir.

    view_zenith_min: float = 0.0
    view_zenith_max: float = 15.0

    # Relative azimuth angle.

    relative_azimuth_min: float = 0.0
    relative_azimuth_max: float = 180.0
