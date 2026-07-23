# ALPHABETIZE fixture

Public smoke-test input for the factory's first named skill,
`ui.sort-dropdown`. `request.md` and both PNG files are synthetic and
sanitized; `expected.json` is the machine-readable acceptance contract.

The source request remains historical provenance under
`/srv/orchestration/projects/software-factory/`. It is not copied here because
Git holds sanitized fixtures only.

The PNGs were produced with the built-in image-editing tool from the two
original UI screenshots. The edit preserved the layout and unsorted dropdown
failure while replacing every employee and customer detail with synthetic
test data. The originals were not modified.

Fixture identities:

- `create-or-assign-school-unsorted.png` - SHA-256
  `1e71d23f7288be62fa72725beac8d02277b2941e7d88d503e404cdc34b9bbdf5`
- `simple-sales-report-unsorted.png` - SHA-256
  `f549cfc3157db7df24b3df03ab40b2242c723976b7b928d5a375178b38bc5684`

Session 7 adds a deterministic implement request and a targeted PHPUnit
source-contract test. The test is committed on the fixture base branch before
the worker runs, so the candidate patch remains the ruled two production files
and three changed lines.
