# Author disposition stage

For every typed review finding, emit exactly one disposition: `concede`,
`refute`, or `escalate`. A refutation requires bounded evidence. The input has
no reviewer transcript or raw request. Emit `DispositionArtifact` JSON only.
