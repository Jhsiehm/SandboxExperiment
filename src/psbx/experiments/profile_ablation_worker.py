"""Independent, provenance-preserving profile ablations; standard-library Docker worker."""

import json
import sys

if __package__:
    from .individual_worker import EXTRA, NEW, SPARSE, SYSTEM, TASK
    from .social_worker import isolation
else:
    from individual_worker import EXTRA, NEW, SPARSE, SYSTEM, TASK
    from social_worker import isolation

REDUCED = SPARSE + ["finance_finpast", "health_insured", "econ_ecpast"]
ARMS = {
    "original_sparse": SPARSE,
    "original_rich": SPARSE + EXTRA,
    "reduced_existing": REDUCED,
    "reduced_plus_observed": REDUCED + NEW,
}
EVIDENCE_KEYS = {
    "label",
    "answer",
    "status",
    "source",
    "source_variable",
    "observed_date",
    "date_precision",
    "missing",
    "inference",
    "exposure",
}


def build_prompt(payload):
    if set(payload) != {"arm", "baseline_date", "observations"}:
        raise ValueError("Unexpected payload keys")
    if payload["arm"] not in ARMS:
        raise ValueError("Unknown arm")
    if set(payload["observations"]) != set(ARMS[payload["arm"]]):
        raise ValueError("Unexpected or missing profile fields")
    for field, value in payload["observations"].items():
        if set(value) != EVIDENCE_KEYS or value["source_variable"] != field:
            raise ValueError("Invalid provenance")
        if not all(isinstance(value[k], str) for k in EVIDENCE_KEYS - {"missing", "inference"}):
            raise ValueError("Provenance values must be strings")
        if value["missing"] != (value["status"] == "missing"):
            raise ValueError("Missingness/status mismatch")
        if value["inference"] is not False or not isinstance(value["missing"], bool):
            raise ValueError("Only measured evidence is allowed")
        if value["exposure"] != "Personal exposure not established by this record":
            raise ValueError("Unsupported exposure claim")
    return {
        "system": SYSTEM,
        "user": json.dumps(
            {"baseline_date": payload["baseline_date"], "observations": payload["observations"]},
            sort_keys=True,
        )
        + "\n"
        + TASK,
    }


if __name__ == "__main__":
    print(json.dumps({**build_prompt(json.load(sys.stdin)), "isolation": isolation()}))
