# ============================================================
# sampler.py
# ============================================================

import numpy as np
import pandas as pd

from scipy.stats import qmc, norm


# ============================================================
# Utility
# ============================================================

def scale(x, low, high):

    return low + x * (high - low)


# ============================================================
# Latin Hypercube
# ============================================================

def latin_hypercube(
    n_samples,
    n_dimensions,
    seed
):

    sampler = qmc.LatinHypercube(
        d=n_dimensions,
        seed=seed
    )

    return sampler.random(
        n=n_samples
    )


# ============================================================
# Generate correlated latent variables
# ============================================================

def generate_correlated_latents(
    n_samples,
    seed
):

    """
    Generates correlated latent variables.

    The latent variables represent broad vegetation states.

    They are NOT directly PROSAIL parameters.

    They are transformed later into biologically meaningful
    PROSAIL parameters.
    """

    rng = np.random.default_rng(seed)

    # Correlation matrix.

    correlation = np.array([
        [1.00,  0.65,  0.55, -0.40],
        [0.65,  1.00,  0.50, -0.35],
        [0.55,  0.50,  1.00, -0.30],
        [-0.40, -0.35, -0.30, 1.00]
    ])

    # Cholesky decomposition.

    L = np.linalg.cholesky(
        correlation
    )

    # Independent standard normal variables.

    z = rng.normal(
        size=(n_samples, 4)
    )

    # Introduce correlations.

    z_correlated = z @ L.T

    # Convert to uniform [0,1].

    u = norm.cdf(
        z_correlated
    )

    return u


# ============================================================
# Vegetation parameter generator
# ============================================================

def generate_parameters(
    n_samples,
    seed
):

    """
    Generate a research-oriented synthetic population.

    Parameters are not independently sampled.

    Several parameters are correlated through latent
    vegetation states.
    """

    # --------------------------------------------------------
    # LHS variables
    # --------------------------------------------------------

    lhs = latin_hypercube(
        n_samples,
        10,
        seed
    )

    # --------------------------------------------------------
    # Correlated latent variables
    # --------------------------------------------------------

    latent = generate_correlated_latents(
        n_samples,
        seed + 100
    )

    # --------------------------------------------------------
    # Growth-stage variable
    #
    # 0 = early vegetation
    # 1 = mature canopy
    #
    # --------------------------------------------------------

    stage = lhs[:, 0]

    # --------------------------------------------------------
    # LAI
    #
    # Beta distribution gives greater density in the middle
    # of the physically meaningful range.
    # --------------------------------------------------------

    lai_u = lhs[:, 1]

    # Beta-like transformation

    lai_base = (
        0.35 * lai_u +
        0.65 * stage
    )

    LAI = (
        0.1 +
        6.9 * lai_base
    )

    # --------------------------------------------------------
    # Chlorophyll
    #
    # Increases with vegetation maturity.
    # --------------------------------------------------------

    Cab = (
        20.0
        + 60.0 * (
            0.35 * latent[:, 0]
            + 0.65 * stage
        )
    )

    # --------------------------------------------------------
    # Carotenoids
    #
    # Correlated with chlorophyll but with independent
    # biological variability.
    # --------------------------------------------------------

    Car = (
        4.0
        + 16.0 * (
            0.65 * latent[:, 1]
            + 0.35 * stage
        )
    )

    # --------------------------------------------------------
    # Water content
    #
    # Related to vegetation state.
    # --------------------------------------------------------

    Cw = (
        0.006
        + 0.024 * (
            0.65 * latent[:, 2]
            + 0.35 * stage
        )
    )

    # --------------------------------------------------------
    # Dry matter
    # --------------------------------------------------------

    Cm = (
        0.004
        + 0.016 * (
            0.5 * latent[:, 3]
            + 0.5 * stage
        )
    )

    # --------------------------------------------------------
    # Brown pigment
    #
    # Low during healthy/mature green stage.
    # Higher during senescence.
    # --------------------------------------------------------

    senescence = np.clip(
        (stage - 0.75) / 0.25,
        0.0,
        1.0
    )

    Cbrown = (
        0.02
        + 0.45 * senescence
        + 0.05 * lhs[:, 2]
    )

    # --------------------------------------------------------
    # Leaf structure parameter
    # --------------------------------------------------------

    N = (
        1.2
        + 1.1 * lhs[:, 3]
    )

    # --------------------------------------------------------
    # Leaf angle
    #
    # 0   = planophile
    # 90  = erectophile
    #
    # We constrain this to a realistic canopy range.
    # --------------------------------------------------------

    LIDFa = (
        20.0
        + 50.0 * lhs[:, 4]
    )

    # --------------------------------------------------------
    # Hotspot parameter
    # --------------------------------------------------------

    Hspot = (
        0.02
        + 0.35 * lhs[:, 5]
    )

    # --------------------------------------------------------
    # Observation geometry
    # --------------------------------------------------------

    TTS = (
        15.0
        + 45.0 * lhs[:, 6]
    )

    TTO = (
        15.0 * lhs[:, 7]
    )

    PSI = (
        180.0 * lhs[:, 8]
    )

    # --------------------------------------------------------
    # Soil parameters
    # --------------------------------------------------------

    Psoil = lhs[:, 9]

    # Soil brightness.

    Rsoil = (
        0.75
        + 0.50 * lhs[:, 5]
    )

    # --------------------------------------------------------
    # Put everything together
    # --------------------------------------------------------

    df = pd.DataFrame({

        "N": N,

        "Cab": Cab,

        "Car": Car,

        "Cbrown": Cbrown,

        "Cw": Cw,

        "Cm": Cm,

        "LAI": LAI,

        "LIDFa": LIDFa,

        "Hspot": Hspot,

        "TTS": TTS,

        "TTO": TTO,

        "PSI": PSI,

        "Psoil": Psoil,

        "Rsoil": Rsoil,

        "growth_stage": stage,

    })

    return df