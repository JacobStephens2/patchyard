# Fixtures

`acceptance/` - sanitized inputs for the factory's own acceptance matrix (pass^k; `acceptance/alphabetize/` is criterion 1's smoke case). `triage/` - sanitized request data plus schema-valid recorded triage outputs; `replay-manifest.json` names the expected lane for every case and runs without a model provider. `bench/` - instruments for model × harness × provider evaluation (the muse-smoke floor probe's heirs, long-spec workloads). Raw requests and screenshots never enter git (A43).
