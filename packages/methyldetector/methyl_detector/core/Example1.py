# Example centroids (replace with your real ones)
cpgs = [
    {'id':'chr1:100', 'aC':6.0,'bC':2.5, 'aH':1.8,'bH':5.2},
    {'id':'chr1:200', 'aC':2.2,'bC':7.0, 'aH':5.8,'bH':2.1},
    {'id':'chr3:150', 'aC':8.0,'bC':2.0, 'aH':2.5,'bH':7.5},
    {'id':'chr5:900', 'aC':1.8,'bC':8.0, 'aH':7.5,'bH':2.2},
    # ...
]

model = select_panel_beta(
    cpgs,
    delta_mu_min=0.10,
    bc_max=0.90,
    tau_min=2.0,
    target_fpr=0.01,
    target_fnr=0.01,
    prior=(0.5,0.5),
    search="binary",                # minimal prefix via binary search
    rank_mode="delta_bc_var",       # <<— precision-weighted ranking you asked for
    rank_gamma=1.0,                 # strength of overlap penalty
    var_pool="sum"                  # pooling for variance penalty
)

print("Panel size:", len(model['panel']))
print("Threshold t:", model['threshold'])
print("Approx FNR:", model['cum_stats']['fnr'])

# Score a new sample (values aligned to model['panel'] order)
values = [0.82, 0.21, 0.88, 0.10][:len(model['panel'])]
res = score_sample_beta(pack_sample(values, model['panel']), model)
print("Decision:", res['decision'], "P(Cancer):", res['P_C'])