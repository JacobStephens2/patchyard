# Dispute arbitration stage

The arbiter receives one typed dispute record and a fresh worktree at the
reviewed SHA. It does not receive author or reviewer transcripts. Empirically
checkable findings must return `experiment_required`; other findings may
return `author` or `reviewer`. Emit `ArbitrationArtifact` JSON only.
