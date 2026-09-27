# ============================================================
# simulator.py
# ============================================================

import numpy as np
import prosail
from concurrent.futures import ProcessPoolExecutor
from srf import convolve_spectrum


# ============================================================
# PROSAIL
# ============================================================

def run_prosail_batch(
    parameters
):

    spectra = []

    print(
        "\nRunning PROSAIL..."
    )

    for i, row in parameters.iterrows():

        spectrum = prosail.run_prosail(

            n=row["N"],

            cab=row["Cab"],

            car=row["Car"],

            cbrown=row["Cbrown"],

            cw=row["Cw"],

            cm=row["Cm"],

            lai=row["LAI"],

            lidfa=row["LIDFa"],

            hspot=row["Hspot"],

            tts=row["TTS"],

            tto=row["TTO"],

            psi=row["PSI"],

            prospect_version="D",

            typelidf=2,

            factor="SDR",

            psoil=row["Psoil"],

            rsoil=row["Rsoil"]
        )

        spectra.append(
            spectrum
        )

        if (i + 1) % 10_000 == 0:

            print(
                f"PROSAIL: "
                f"{i + 1:,} / "
                f"{len(parameters):,}"
            )

    return np.asarray(
        spectra
    )


# ============================================================
# Add measurement noise
# ============================================================

def add_reflectance_noise(
    reflectance,
    std,
    seed
):

    rng = np.random.default_rng(
        seed
    )

    noise = rng.normal(
        loc=0.0,
        scale=std,
        size=reflectance.shape
    )

    noisy = (
        reflectance +
        noise
    )

    # Reflectance physically constrained.

    noisy = np.clip(
        noisy,
        0.0,
        1.0
    )

    return noisy


def _simulate_chunk(parameters, wavelengths, srf):
    """Convolve each spectrum immediately; never retain an n×2101 matrix."""
    bands = list(srf)
    observations = np.empty((len(parameters), len(bands)), dtype=np.float64)
    for i, (_, row) in enumerate(parameters.iterrows()):
        spectrum = prosail.run_prosail(n=row["N"], cab=row["Cab"], car=row["Car"], cbrown=row["Cbrown"], cw=row["Cw"], cm=row["Cm"], lai=row["LAI"], lidfa=row["LIDFa"], hspot=row["Hspot"], tts=row["TTS"], tto=row["TTO"], psi=row["PSI"], prospect_version="D", typelidf=2, factor="SDR", psoil=row["Psoil"], rsoil=row["Rsoil"])
        result = convolve_spectrum(spectrum, wavelengths, srf)
        observations[i] = [result[band] for band in bands]
    return observations, bands


def run_prosail_to_sentinel2_batch(parameters, wavelengths, srf, completed=0, total=None, workers=1):
    """Convolve immediately, distributing parameter chunks across processes."""
    workers = max(1, min(workers, len(parameters)))
    print(f"\nRunning PROSAIL and Sentinel-2 convolution ({workers} process(es))...")
    if workers == 1:
        observations, bands = _simulate_chunk(parameters, wavelengths, srf)
    else:
        index_chunks = np.array_split(np.arange(len(parameters)), workers)
        chunks = [parameters.iloc[indexes].copy() for indexes in index_chunks if len(indexes)]
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(
                _simulate_chunk,
                chunks,
                [wavelengths] * len(chunks),
                [srf] * len(chunks),
            ))
        observations = np.vstack([result[0] for result in results])
        bands = results[0][1]
    done = completed + len(parameters)
    print(f"  Completed {done:,}" + (f" / {total:,}" if total else ""))
    return observations, bands
