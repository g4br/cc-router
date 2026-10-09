# Optional local Laya backend

The bundled `config/ladder.json` ships with `backend: laya`, but the Laya difficulty
gate is not validated yet. `install.py` asks (default no, or `--backend laya|heuristic`)
before it installs Laya and downloads the public English checkpoint.
Routing never starts it during a unit test or ordinary decision: the skill runs
`start_services.sh --check` on invocation and asks the user before starting. The operator supplies a faithful English summary
and keeps the user's language for reports.

## Installation and startup

```bash
python3 -m pip install "laya[serve]"
scripts/start_services.sh
```

Startup may download the public checkpoint and requires user-authorized network
access. It probes available GPUs in a separate process and falls back to CPU.
The existing launcher, `serve_laya.py` and `laya_device.py` are retained. Routing
itself depends only on Python standard library.

The launcher uses `CC_ROUTER_CONFIG`, then `config/router.json` if present, then
`config/ladder.json`. Use the configured local port (the bundled file currently
uses 8001). If occupied by another service, it asks before changing ports; a yes
backs up the configuration and updates `laya_url`/`laya_urls`. An empty answer
changes nothing. The log remains under `${XDG_STATE_HOME:-~/.local/state}/cc-router`.

Set `backend` to `laya` and include the intended hosts in
`laya_enabled_operators`. One local instance can serve both. The optional
`LAYA_API_KEY` authenticates this local service only; it is not a provider billing
credential. The selector accepts only loopback HTTP URLs, disables proxy use and
rejects redirects. It does not contact model-provider APIs.

## Scores and observational calibration

The request contains only description, operation, files, ambiguity and criticality.
It excludes user language, execution controls, targets, credentials and history.
Questions are generated from **eligible** candidate profiles. Only the explicit
local authentication header, if configured, carries the Laya credential.

To cancel position bias, each question is sent twice in the same request, with `criteria`
in the order A,B and B,A (laya-serve renders options in key order). The score is the mean
of the two "A" (yes) probabilities. `option_order` was not used or verified.

The returned number is an **uncalibrated score**, not a guaranteed probability of
success. `success_threshold` remains a transitional heuristic. If no eligible
candidate clears it, use the conservative heuristic and report `laya (no opinion)`.
An unavailable service reports `heuristic (laya unavailable)`; malformed JSON,
missing/invalid scores and HTTP contract errors stop visibly. They never masquerade
as successful fallback.

Observed calibration partitions scores into ten bins, separately by task profile,
host, effective candidate, resolved version and effort. At least
`min_calibration_samples` (default 20) labelled outcomes in the current bin are
required. The event's `no_rework` label, including later feedback, determines
first-pass success. Calibration reports a Laplace-smoothed estimate and Wilson
95% interval. With enough data, selection uses the calibrated lower bound for its
reliability constraint; otherwise it retains the labelled heuristic score and
conservative fallback. Sparse observations never become a numeric success guarantee.

Completion resources are estimated independently from verified history. No tokens
are divided by an uncalibrated score. The [v2 reference](router-v2.md) documents
sample sufficiency, version separation, sources/units and policy weights. Unknown
versions and incomplete metrics cannot drive empirical selection.

The public checkpoint is not trained or fine-tuned by this project. Outcomes of
selected candidates do not establish how untried alternatives would have performed.
Tests use a small local mock HTTP server and do not load the checkpoint.
