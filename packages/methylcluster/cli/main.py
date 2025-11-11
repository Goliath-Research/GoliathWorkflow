from __future__ import annotations

import argparse
from pathlib import Path
from typing import List
import csv

import numpy as np

from methyl_utils.methyl_sample import MethylSample
from methyl_cluster.methyl_cluster_dp import MethylClusterDP, DPConfig


def _load_samples(sample_paths: List[Path]) -> List[MethylSample]:
	samples: List[MethylSample] = []
	for p in sample_paths:
		samples.append(MethylSample.load_from_h5(p))
	return samples


def run():
	parser = argparse.ArgumentParser(description="DP clustering of methylation samples into homogeneous centroids (per chromosome).")
	parser.add_argument("--samples-file", required=True, help="Text file with one sample HDF5 path per line.")
	parser.add_argument("--output-dir", required=True, help="Directory to write centroids and assignments.")
	parser.add_argument("--alpha-dp", type=float, default=1.0)
	parser.add_argument("--a0", type=float, default=1.0)
	parser.add_argument("--b0", type=float, default=1.0)
	parser.add_argument("--n-switch", type=int, default=20)
	parser.add_argument("--max-sweeps", type=int, default=50)
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument("--no-gpu", action="store_true", help="Disable GPU even if available.")
	args = parser.parse_args()

	sample_paths = [Path(line.strip()) for line in Path(args.samples_file).read_text().splitlines() if line.strip()]
	output_dir = Path(args.output_dir)
	output_dir.mkdir(parents=True, exist_ok=True)

	cfg = DPConfig(
		alpha_dp=args.alpha_dp,
		a0=args.a0,
		b0=args.b0,
		n_switch=args.n_switch,
		use_gpu=(not args.no_gpu),
		max_sweeps=args.max_sweeps,
		seed=args.seed,
	)
	cluster = MethylClusterDP(cfg)

	# Load samples
	samples = _load_samples(sample_paths)

	# Fit clustering
	cluster.fit(samples, init="random")

	# Save assignments (sample_path, centroid_idx starting at 1)
	assign_csv = output_dir / "assignments.csv"
	with assign_csv.open("w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["sample_path", "centroid_idx"])
		for p, k in zip(sample_paths, cluster.assign):
			writer.writerow([str(p), int(k) + 1])

	# Save centroids as centroid-{idx}.h5 (idx starting at 1)
	for idx, c in enumerate(cluster.centroids, start=1):
		out_path = output_dir / f"centroid-{idx}.h5"
		c.save_to_h5(out_path)


if __name__ == "__main__":
	run()


