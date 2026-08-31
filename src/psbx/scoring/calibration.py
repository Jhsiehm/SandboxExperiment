from __future__ import annotations

from psbx.schemas import CalibrationBin, CalibrationResult, Prediction, Question


def calibration_curve(
    preds: list[Prediction],
    qs: dict[str, Question],
    n_bins: int = 10,
) -> CalibrationResult:
    bins: list[list[Prediction]] = [[] for _ in range(n_bins)]
    for p in preds:
        idx = min(n_bins - 1, int(p.probability * n_bins))
        bins[idx].append(p)
    out: list[CalibrationBin] = []
    ece = 0.0
    n = len(preds) or 1
    for i, group in enumerate(bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not group:
            out.append(CalibrationBin(lo=lo, hi=hi, mean_forecast=0.0, mean_outcome=0.0, n=0))
            continue
        mean_f = sum(p.probability for p in group) / len(group)
        mean_o = sum(1.0 if qs[p.question_id].ground_truth else 0.0 for p in group) / len(group)
        out.append(
            CalibrationBin(lo=lo, hi=hi, mean_forecast=mean_f, mean_outcome=mean_o, n=len(group))
        )
        ece += (len(group) / n) * abs(mean_f - mean_o)
    return CalibrationResult(n_bins=n_bins, bins=out, ece=ece)
