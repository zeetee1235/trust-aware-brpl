# Pre-main quickcheck (2026-03-28)

## Runs executed
1. Baseline (v13.12 original, no NA strict guard), medium only
- results: `results/random_topo_quick_v1312_baseline_medium`
- size: 5 topo x 3 seeds x 2 proto = 30 runs

2. Current patched candidate, medium+sparse+dense
- results: `results/random_topo_quick_fixed_sparse_dense`
- size: 3 densities x 5 topo x 3 seeds x 2 proto = 90 runs

Attack profile for all above: `sinkhole_drop` (verified from sim.log and manifest).

## Medium baseline re-check (original v13.12)
- Delta(att_share): -0.0370
- Delta(hit_ratio): -0.0216
- Delta(churn): +0.1529
- Delta(PDR_dur): -0.0203

## Medium current candidate
- Delta(att_share): -0.0438
- Delta(hit_ratio): -0.0431
- Delta(churn): +0.1020
- Delta(PDR_dur): -0.0109

## Medium change vs baseline (candidate - baseline)
- Delta(att_share): -0.0068 (better isolation)
- Delta(hit_ratio): -0.0216 (better isolation)
- Delta(churn): -0.0510 (lower overhead)
- Delta(PDR_dur): +0.0094 (less PDR loss)

## Current candidate by density (5 topo each)
- sparse: Delta(att_share)=-0.0057, Delta(hit_ratio)=-0.0078, Delta(churn)=+0.0431, Delta(PDR_dur)=+0.0449
- medium: Delta(att_share)=-0.0438, Delta(hit_ratio)=-0.0431, Delta(churn)=+0.1020, Delta(PDR_dur)=-0.0109
- dense: Delta(att_share)=-0.0140, Delta(hit_ratio)=-0.0137, Delta(churn)=+0.0020, Delta(PDR_dur)=+0.0012
- overall(15 topo): Delta(att_share)=-0.0212 [95% CI -0.0344, -0.0079], Delta(hit_ratio)=-0.0216, Delta(churn)=+0.0490, Delta(PDR_dur)=+0.0117

## Readout
- Mean direction for primary isolation metrics is improved in all three densities.
- But per-density confidence for sparse/dense remains weak with only 5 topologies (CIs cross zero for att_share/hit_ratio there).
- Churn is still positive, but far lower than earlier medium baseline.

## Recommendation before full main run
1. Proceed is possible now (signal direction is consistent), but treat this as go-with-risk.
2. If time allows, increase quickcheck to >=10 topologies per density before launching 750/1500 full matrix.
3. If proceeding immediately, keep current candidate fixed and run full random matrix with `--attack-profile sinkhole_drop`.
