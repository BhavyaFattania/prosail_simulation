"""Stream a PROSAIL Sentinel-2 lookup table to CSV in memory-safe batches."""
import argparse
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
from config import Config
from sampler import generate_parameters
from simulator import add_reflectance_noise, run_prosail_to_sentinel2_batch
from srf import load_srf_excel


def parse_args():
    defaults = Config()
    parser = argparse.ArgumentParser(description="Generate a streaming PROSAIL Sentinel-2 LUT.")
    parser.add_argument("--samples", type=int, default=defaults.n_samples)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--workers", type=int, default=4,
                        help="parallel PROSAIL worker processes (default: 4)")
    parser.add_argument("--output", type=Path, default=defaults.output_file)
    parser.add_argument("--platform", choices=("S2A", "S2B", "S2C"), default=defaults.platform)
    parser.add_argument("--no-noise", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing output CSV")
    args = parser.parse_args()
    if args.samples < 1 or args.batch_size < 1 or args.workers < 1:
        parser.error("--samples, --batch-size, and --workers must all be at least 1")
    return args


def main():
    args = parse_args()
    config = replace(Config(), n_samples=args.samples, output_file=args.output,
                     platform=args.platform, add_noise=not args.no_noise)
    config.output_file.parent.mkdir(parents=True, exist_ok=True)
    if config.output_file.exists() and not args.overwrite:
        raise FileExistsError(f"Output exists: {config.output_file}. Use --overwrite to replace it.")
    temporary_output = config.output_file.with_suffix(config.output_file.suffix + ".part")
    if temporary_output.exists():
        temporary_output.unlink()

    wavelengths = np.arange(config.wavelength_start, config.wavelength_end + 1, config.wavelength_step)
    srf = load_srf_excel(config.srf_file, config.sentinel_bands, config.platform)
    print(f"Generating {config.n_samples:,} rows in batches of {args.batch_size:,}.")
    rows_written = invalid_rows = 0
    first_batch = True
    for batch_index, start in enumerate(range(0, config.n_samples, args.batch_size)):
        size = min(args.batch_size, config.n_samples - start)
        print(f"\nBatch {batch_index + 1}: rows {start + 1:,}-{start + size:,}")
        parameters = generate_parameters(size, config.random_seed + batch_index)
        values, bands = run_prosail_to_sentinel2_batch(
            parameters, wavelengths, srf, start, config.n_samples, args.workers
        )
        if config.add_noise:
            values = add_reflectance_noise(values, config.noise_std, config.random_seed + 500 + batch_index)
        dataset = pd.concat([parameters.reset_index(drop=True), pd.DataFrame(values, columns=bands)], axis=1).dropna()
        invalid_rows += size - len(dataset)
        dataset.loc[:, bands] = dataset[bands].clip(0.0, 1.0)
        dataset.to_csv(temporary_output, mode="w" if first_batch else "a", header=first_batch, index=False)
        first_batch = False
        rows_written += len(dataset)
        del parameters, values, dataset

    temporary_output.replace(config.output_file)
    columns = pd.read_csv(config.output_file, nrows=0).columns.tolist()
    print(f"\nSynthetic LUT generated: {rows_written:,} rows, {len(columns)} columns")
    print(f"Invalid rows removed: {invalid_rows}")
    print(f"File: {config.output_file}")


if __name__ == "__main__":
    main()
