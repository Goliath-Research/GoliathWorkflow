from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict

import numpy as np

# Lazy imports to avoid circular deps at import time
try:
	from methyl_utils import MethylSample
except Exception:  # pragma: no cover
	MethylSample = None  # type: ignore


@dataclass
class DPConfig:
	alpha_dp: float = 1.0          # CRP concentration
	a0: float = 1.0                # Beta prior (can be per-site later)
	b0: float = 1.0
	n_switch: int = 20             # Beta-Binomial (<=) vs Beta (>)
	use_gpu: bool = True           # honor GPU path in methyl_utils
	max_sweeps: int = 50
	burn_in: int = 10
	thin: int = 1
	seed: int = 42


class MethylClusterDP:
	"""
	Dirichlet-Process mixture over methylation centroids with Beta/Beta-Binomial emissions.

	Functional centroid API:
	- Centroids are MethylSample objects (extended/baseline).
	- Updates are done via MethylSample.add_sample/remove_sample returning NEW centroids.
	"""

	def __init__(self, config: DPConfig):
		self.cfg = config
		self.centroids: List[MethylSample] = []
		self.assign: Optional[np.ndarray] = None
		self.Nk: Optional[np.ndarray] = None
		self.history_: Dict[str, list] = {"K": [], "ll": []}
		self._rng = np.random.default_rng(self.cfg.seed)

	# ---------- Public API ----------

	def fit(
		self,
		samples: List["MethylSample"],
		init: str = "seeded",
		seeded_groups: Optional[List[List[int]]] = None
	) -> "MethylClusterDP":
		"""
		Run collapsed-Gibbs with functional centroid updates.
		- init='seeded': seeded_groups is a list of lists of indices; each forms a starting centroid
		- init='random': random small partition (2 clusters)
		"""
		if MethylSample is None:  # pragma: no cover
			raise ImportError("MethylSample not available; ensure methyl_utils is importable.")

		n = len(samples)
		assert n > 0

		if init == "seeded":
			assert seeded_groups is not None and len(seeded_groups) > 0
			self.centroids = [
				MethylSample.create_centroid_from_samples(
					[samples[i] for i in grp],
					use_gpu=self.cfg.use_gpu
				)
				for grp in seeded_groups
			]
			self.assign = np.empty(n, dtype=int)
			for k, grp in enumerate(seeded_groups):
				self.assign[grp] = k
			# Assign any unassigned to nearest existing cluster
			all_seeded = np.concatenate(seeded_groups) if len(seeded_groups) > 0 else np.array([], dtype=int)
			unassigned = np.where(~np.isin(np.arange(n), all_seeded))[0]
			for i in unassigned:
				k = self._argmax_existing_logprob(samples[i])
				self.assign[i] = k
		else:
			# random 2-way split
			self.assign = self._rng.integers(0, 2, size=n)
			self.centroids = [
				self._build_centroid([samples[i] for i in np.where(self.assign == k)[0]])
				for k in range(2)
			]

		self._refresh_counts()

		# Gibbs sweeps
		for _ in range(self.cfg.max_sweeps):
			order = self._rng.permutation(n)
			for i in order:
				self._reassign_one(samples, i)

			self.history_["K"].append(len(self.centroids))
			self.history_["ll"].append(self._joint_log_predictive(samples))

		return self

	def predict(self, samples: List["MethylSample"]) -> np.ndarray:
		"""MAP cluster index per sample under the fitted model."""
		return np.array([self._argmax_existing_logprob(s) for s in samples], dtype=int)

	def predict_log_proba(self, samples: List["MethylSample"]) -> np.ndarray:
		"""Log posterior over existing clusters (no 'new' component here)."""
		K = len(self.centroids)
		out = np.empty((len(samples), K), dtype=float)
		for i, s in enumerate(samples):
			scores = [self._log_cluster_weight(k) + self._log_pred_lik(self.centroids[k], s) for k in range(K)]
			m = np.max(scores)
			z = m + np.log(np.sum(np.exp(np.array(scores) - m)))
			out[i, :] = np.array(scores) - z
		return out

	# ---------- Internal helpers ----------

	def _build_centroid(self, sample_list: List["MethylSample"]) -> "MethylSample":
		return MethylSample.create_centroid_from_samples(sample_list, use_gpu=self.cfg.use_gpu)

	def _refresh_counts(self):
		K = len(self.centroids)
		self.Nk = np.zeros(K, dtype=int)
		for k in range(K):
			self.Nk[k] = int(np.sum(self.assign == k))

	def _reassign_one(self, samples: List["MethylSample"], i: int):
		k_old = int(self.assign[i])

		# Leave-one-out update for the old cluster
		if self.Nk[k_old] > 1:
			self.centroids[k_old] = self.centroids[k_old].remove_sample(samples[i], use_gpu=self.cfg.use_gpu)
			self.Nk[k_old] -= 1
		else:
			self._delete_cluster(k_old)

		# Compute assignment among existing clusters + 'new'
		log_scores = []
		for k in range(len(self.centroids)):
			log_scores.append(self._log_cluster_weight(k) + self._log_pred_lik(self.centroids[k], samples[i]))
		# New cluster prior-predictive
		log_new = np.log(self.cfg.alpha_dp) + self._log_prior_pred_lik(samples[i])
		log_scores.append(log_new)

		k_star = self._categorical_from_logs(log_scores)
		if k_star == len(self.centroids):
			# new cluster
			new_c = self._build_centroid([samples[i]])
			self.centroids.append(new_c)
			self.assign[i] = len(self.centroids) - 1
		else:
			# add to existing
			self.centroids[k_star] = self.centroids[k_star].add_sample(samples[i], use_gpu=self.cfg.use_gpu)
			self.assign[i] = k_star

		self._refresh_counts()

	def _delete_cluster(self, k: int):
		del self.centroids[k]
		mask = self.assign > k
		self.assign[mask] -= 1

	def _log_cluster_weight(self, k: int) -> float:
		# CRP weight ∝ Nk
		return float(np.log(max(int(self.Nk[k]), 1e-12)))

	def _log_pred_lik(self, centroid: "MethylSample", sample: "MethylSample") -> float:
		"""
		Summed log predictive likelihood under centroid:
		- For coverage n <= n_switch: Beta-Binomial(m|n, a, b)
		- Else: Beta PDF over methylation level x with (a,b)
		"""
		# Intersect positions
		common_pos = np.intersect1d(centroid.pos, sample.pos, assume_unique=True)
		if len(common_pos) == 0:
			return float(-1e9)  # effectively impossible

		c_idx = np.searchsorted(centroid.pos, common_pos)
		s_idx = np.searchsorted(sample.pos, common_pos)

		alpha_c = centroid.alpha[c_idx]
		beta_c = centroid.beta[c_idx]

		# Sample counts
		mC = sample.mC[s_idx]
		uC = sample.uC[s_idx]
		n = mC + uC

		# Valid coverage
		valid = n > 0
		if not np.any(valid):
			return float(-1e9)

		nv = n[valid].astype(np.int64, copy=False)
		kv = mC[valid].astype(np.int64, copy=False)
		av = alpha_c[valid].astype(np.float64, copy=False)
		bv = beta_c[valid].astype(np.float64, copy=False)

		# Switch rule
		mask_bb = nv <= self.cfg.n_switch
		log_sum = 0.0

		if np.any(mask_bb):
			from methyl_utils.beta_analytics import log_beta_binomial_pmf
			log_bb = log_beta_binomial_pmf(
				kv[mask_bb], nv[mask_bb], av[mask_bb], bv[mask_bb], use_gpu=self.cfg.use_gpu
			)
			log_sum += float(np.sum(log_bb))

		if np.any(~mask_bb):
			from methyl_utils.beta_analytics import beta_log_pdf
			x = kv[~mask_bb] / nv[~mask_bb]
			log_pdf = beta_log_pdf(x.astype(np.float64), av[~mask_bb], bv[~mask_bb], use_gpu=self.cfg.use_gpu)
			log_sum += float(np.sum(log_pdf))

		return float(log_sum)

	def _log_prior_pred_lik(self, sample: "MethylSample") -> float:
		"""
		Summed log prior-predictive for spawning a new cluster using Beta(a0,b0).
		Same switch rule as _log_pred_lik, but with constant (a0,b0).
		"""
		n = sample.mC + sample.uC
		valid = n > 0
		if not np.any(valid):
			return float(-1e9)

		nv = n[valid].astype(np.int64, copy=False)
		kv = sample.mC[valid].astype(np.int64, copy=False)
		a0 = np.full_like(kv, float(self.cfg.a0), dtype=np.float64)
		b0 = np.full_like(kv, float(self.cfg.b0), dtype=np.float64)

		mask_bb = nv <= self.cfg.n_switch
		log_sum = 0.0

		if np.any(mask_bb):
			from methyl_utils.beta_analytics import log_beta_binomial_pmf
			log_bb = log_beta_binomial_pmf(
				kv[mask_bb], nv[mask_bb], a0[mask_bb], b0[mask_bb], use_gpu=self.cfg.use_gpu
			)
			log_sum += float(np.sum(log_bb))

		if np.any(~mask_bb):
			from methyl_utils.beta_analytics import beta_log_pdf
			x = kv[~mask_bb] / nv[~mask_bb]
			log_pdf = beta_log_pdf(x.astype(np.float64), a0[~mask_bb], b0[~mask_bb], use_gpu=self.cfg.use_gpu)
			log_sum += float(np.sum(log_pdf))

		return float(log_sum)

	def _argmax_existing_logprob(self, sample: "MethylSample") -> int:
		scores = [self._log_cluster_weight(k) + self._log_pred_lik(c, sample) for k, c in enumerate(self.centroids)]
		return int(np.argmax(scores))

	def _categorical_from_logs(self, logw: List[float]) -> int:
		m = np.max(logw)
		w = np.exp(np.array(logw) - m)
		p = w / w.sum()
		return int(self._rng.choice(len(p), p=p))

	def _joint_log_predictive(self, samples: List["MethylSample"]) -> float:
		"""
		Monitoring metric: sum_i log ( sum_k Nk * p(x_i|k) + alpha * p(x_i|new) ).
		Expensive; consider subsampling in production.
		"""
		out = 0.0
		n = len(samples)
		denom = max((n - 1 + self.cfg.alpha_dp), 1e-12)
		for s in samples:
			terms = [self.Nk[k] * np.exp(self._log_pred_lik(self.centroids[k], s)) for k in range(len(self.centroids))]
			terms.append(self.cfg.alpha_dp * np.exp(self._log_prior_pred_lik(s)))
			out += float(np.log(max(np.sum(terms) / denom, 1e-300)))
		return float(out)


