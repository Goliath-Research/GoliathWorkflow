Summary of what was implemented:

**1a – MethylExtendedCentroid (count columns removed)**  
- Dropped optional count columns from the extended centroid: no `sum_mC`, `sum_uC`, `sum_cov`, `sum_cov2`, `sum_mC2`, `sum_uC2`, `Sx3`, `Sx4`, `count_zero`, `count_one`.  
- Removed their getters and all handling in `add_sample`/`remove_sample`/`to_numpy`.  
- Introduced `METHYL_EXTENDED_ONLY_DTYPE` (no count fields) and use it in `MethylExtendedCentroid.to_numpy()`.  
- `METHYL_EXTENDED_CENTROID_DTYPE` is now `METHYL_EXTENDED_ONLY_DTYPE` plus the count fields (for Beta-Binomial).

**1b – MethylBetaBinomialCentroid**  
- New subclass of `MethylExtendedCentroid` in [methyl_frame.py](packages/methylutils/methyl_utils/core/methyl_frame.py) with **required** count columns.  
- Properties: `sum_mC`, `sum_uC`, `sum_cov`, `sum_cov2`, `sum_mC2`, `sum_uC2`, `Sx3`, `Sx4`, `count_zero`, `count_one`, `alpha_bb`, `beta_bb`, and virtual `mean` (α/(α+β), 0/1 safe).  
- `overlap(other)` using Bhattacharyya coefficient.  
- `add_sample` / `remove_sample` / `to_numpy` implemented with full count-column handling.

**1c – Builder and IO**  
- [centroid_builder.py](packages/methylutils/methyl_utils/core/centroid_builder.py): `finalize()` returns `MethylBetaBinomialCentroid` when `store_extended_stats=True`, and `MethylExtendedCentroid` when `False`.  
- [io.py](packages/methylutils/methyl_utils/core/io.py): `load_from_h5` returns `MethylBetaBinomialCentroid` when all Beta-Binomial count columns are present, otherwise `MethylExtendedCentroid`.

**2 – Distribution views**  
- New [distribution_views.py](packages/methylutils/methyl_utils/core/distribution_views.py): protocol `MethylDistributionView` (parameters, mean, overlap) and five views: `CountsView`, `NormalView`, `BetaView`, `BetaBinomialView`, `BMMView`, all 0/1 safe.  
- `get_distribution_view(centroid, mode, positions=None)` builds the right view for mode `counts` | `normal` | `beta` | `beta_binomial` | `beta_mixture`.

**3 – MethylBetaMixtureCentroid**  
- In [methyl_mixture_centroid.py](packages/methylutils/methyl_utils/core/methyl_mixture_centroid.py): added virtual `mean` (weighted component means, clipped) and `overlap(other)` (1 − |mean_self − mean_other| clipped to [0, 1]).

**4 – Probability and overlap helpers**  
- `log_probability_sample_given_centroid(sample, centroid, mode, positions=..., use_gpu=False)` for modes counts / normal / beta / beta_binomial (0/1 safe).  
- `overlap_between_centroids(centroid1, centroid2, mode, positions=None)` using the chosen view’s overlap.

**5 – Shared 0/1 handling**  
- New [methyl_distribution_utils.py](packages/methylutils/methyl_utils/core/methyl_distribution_utils.py) with `clip_beta_params_for_bounds(alpha, beta, min_param=1e-6, max_param=1e6)`.  
- Used in `BetaView`, `BetaBinomialView`, and `_estimate_beta_params_bounded` in statistical_tests.

**6 – Exports**  
- [__init__.py](packages/methylutils/methyl_utils/__init__.py): exports `MethylBetaBinomialCentroid`, `get_distribution_view`, `log_probability_sample_given_centroid`, `overlap_between_centroids`, `CountsView`, `NormalView`, `BetaView`, `BetaBinomialView`, `BMMView`, `clip_beta_params_for_bounds`.

Existing callers that use `getattr(centroid, "sum_cov", None)` (e.g. methyl_centroid_pair) continue to work: they get `None` for `MethylExtendedCentroid` and the real series for `MethylBetaBinomialCentroid`. Tests use `isinstance(..., MethylExtendedCentroid)`, which still holds for `MethylBetaBinomialCentroid`.