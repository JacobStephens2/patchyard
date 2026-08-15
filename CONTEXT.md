# Patchyard Factory

The factory ships software through model-driven pipelines governed by a
human-adjudicated decision log. This glossary fixes terms that have been
resolved; vocabulary still under discussion is deliberately absent.

## Credential qualification

**Requirement**:
One of the six credential-lifecycle properties a provider must demonstrate.
_Avoid_: fixture, test, check, criterion

**Proven**:
The state of a requirement whose result has been committed and accepted.
_Avoid_: qualified, passed, satisfied, met

**Qualified**:
The state of a provider all six of whose requirements are proven.
_Avoid_: proven, verified, approved, certified

**Result**:
The committed file recording one attended run of one requirement.
_Avoid_: fixture, artifact, record, evidence used as a countable noun

**Evidence**:
What a result contains, taken together and never counted.
_Avoid_: naming a file or a quantity

**Receipt**:
A provider-issued record of one interaction with that provider.
_Avoid_: attestation, observation, log entry

**Attestation**:
An operator-recorded observation of a control-plane change for which no receipt
can be obtained.
_Avoid_: receipt, witness, sign-off, manual record

**Control-plane mutation**:
A change to provider-side configuration governing credential trust or spend.
_Avoid_: config change, admin action, setting

**Baseline control**:
A positive control made before a control-plane mutation, which shows that the
path worked before the change.
_Avoid_: pre-mutation positive, prior check, warm-up

**Bracketing control**:
A positive control paired with a denial, which shows that the mutation caused
the denial.
_Avoid_: post-mutation positive, confirmation, sanity check

**Provenance mark**:
A machine-readable statement that a result or an attestation does not rest on a
provider receipt.
_Avoid_: marker, flag, tag, annotation

**Qualified image inventory**:
The worker image files, by name and digest, that a result's evidence ran under.
_Avoid_: recipe digest, image hash, manifest, snapshot

**Descriptor / assembler**:
A descriptor is an inventory file that describes what the guest contains, and is
bound by its digest; the assembler is the program that builds the guest, and is
bound by its effects. Residency is not the test - `pins.env` and the
`*-packages.txt` files are host-side descriptors.
_Avoid_: host file, build script, guest file

**Signing identity**:
The key pair one provider's issuer trusts to sign assertions, together with the
control-plane path holding its private half. One per provider - two providers on
one signing identity means a rotation for either silently unqualifies the other.
_Avoid_: signing key, key file, kid, credential

**Fixture**:
A committed input to a test or a checker, never a record of a live run.
_Avoid_: naming a result, a requirement, or a proof
