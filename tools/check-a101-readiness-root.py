#!/usr/bin/env python3
"""Workflow-rooted source, import, and gate census for A101 readiness."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import re
import sys
import sysconfig


REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github/workflows/infrastructure.yml"
BOUND_SOURCES = {
    "infra/wait-do-worker-firewall.sh": "5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba",
    "infra/replace-worker.sh": "27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e",
    "infra/tofu.sh": "5863f9a885bf1add664592e118fa8b066920be6ef28dc0deb762ac3553e70b7f",
    "infra/ansible/converge.sh": "30a8758d6925ffa7635212cc49c67719ba7a6abf6d389481da2e422dec41f63e",
    "infra/ansible/qualify.sh": "2423bb69fe19e355458158b4b49a67917dac0279bfe76110256944974533dd49",
    "infra/ansible/inventory/tofu.sh": "7101838ae5f3eae5031c30888ae6eda754d9519f6af9d2d6884142155f69bb59",
    "infra/tool-versions.env": "63fa7fa217d98d914a73394c98b41f97571c5c776b3a9b2d4c51d95e56ab917f",
    "tools/read-infra-tool-version.py": "d94d97d605736d0201d0fc0517e0e780d6c346ab79ddc3bd84de7b472edeccd8",
    "tools/install-shellcheck.sh": "715047c90f6a877c57a5495f1bc24feecd40f365ccd8239a6dc711be22a3f535",
    "tools/check-infra.sh": "61ec9e3485ce0933ce7a5a74a81512e8438f6d8a4e00a2d018369e18a827c265",
    "tools/check-ansible.sh": "f702dd84863bbc1973edbb41f21c95d8467cf703d6174e277418c44d92bf2d29",
    "tools/run-isolated-unittest.py": "9291cee8008ce693ad0c891271450606d5f547e4be0821867ac81b95d7d6572f",
    "tools/check-anthropic-spend.py": "8c31bb1e3a1f350a4641a180642c4c43a6de0c2359ec54aad7e76c9a69767a1c",
    "tools/check-anthropic-issuance.py": "56a84e7f5aab1f8a99003a5321ad7d6f910d72fcd35d68166958bd3495e9ee60",
    "tools/check-independence.py": "baaa2e5058862a253c5042e7ccaea4bfea8af05a93825f5ce5cf99bbd1f93782",
    "tools/check-preview-runtime.py": "2f9a6e994c3d50e7e1f729546b3180330c4ccf0d471ee5b75f016cbbc95292be",
    "tools/check-stack.py": "ddce869a4bd4983c35c1b246ba01b5e8b1ea25219c761ebbdb2d5b4a8194deff",
    "tools/check-worker-qualification.py": "357d756da3c83004db6766956a8c31b9682953a50b470dbb3ff7b9acb879e99a",
    "tools/check-worker-runtime.py": "db1646d9bcf738d1df35679e131b1afdb9e35af73be1859d85c8f4017385ce75",
    "infra/ansible/tests/test_a101_readiness_root.py": "2f3ad2be6e2d1c5793064cb307ab7adeac7233e10e22dbdf54cd53402730fde4",
    "infra/ansible/tests/test_worker_firewall_readiness.py": "65ae6c632e521f264c26f243403901897d786efce83c4b115c98bce6cf198996",
    "infra/ansible/tests/test_anthropic_spend.py": "3fbf232fa47c590c845b7205a34027f24451cd0c0dc857f1981f8b352f590355",
    "infra/ansible/tests/test_anthropic_issuance.py": "411f298e3214068b24467d65d7a2dccf750e05952779f072a45fba3c503b8f73",
    "infra/ansible/tests/test_anthropic_wif_admin.py": "8022b0556ef07070069f9d88e57962291d406ab63c448c91799de84d17784cfa",
    "infra/ansible/tests/test_child_launcher.py": "bff549994263407f9b96ec52383b120a159de2c987e2bada49ad13a99c6cd9c0",
    "infra/ansible/tests/test_cloud_init_bootstrap.py": "c0c79b21c2f0ed236667fc8176c1c834f1753991fef35ef6a03f4a21fe6bca04",
    "infra/ansible/tests/test_dashboard_checkout.py": "3f953bb76b11d9d8f8853310fb99938437691024f59a6c55aa5b5fb5cafefcad",
    "infra/ansible/tests/test_log_secret_scan.py": "b4bfc17273cdcafaef18dd5dc3088f0e7aa06faba3d1015cbe74804c2ec5518b",
    "infra/ansible/tests/test_preview_capability_deployment.py": "f8b44dfa110c4f099711487729e5afd222ae6218beb487d5a31d39a6ee580481",
    "infra/ansible/tests/test_replace_worker.py": "d04bb7e7351f865ba47d9cbd3acf3633eda6c4a3d0f1e9807598282c785635fb",
    "infra/ansible/tests/test_session14_qualification.py": "4a121aeec4dff797e67f2a4d5f151c5a0a3f080cdef3499f0ab8f3fef84f41d3",
    "infra/ansible/tests/test_session15_proposer.py": "f66e21999bb5ede882371069de17256361fb7eea9738bc8fa97fcc5cf4f86a0e",
    "infra/ansible/tests/test_session16_cutover.py": "a93f1c4b4a844222473ce787ce4e5430621c3c496b049621d38e051bbe976ba3",
}
EXPECTED_TEST_FILES = (
    "infra/ansible/tests/test_a101_readiness_root.py",
    "infra/ansible/tests/test_worker_firewall_readiness.py",
    "infra/ansible/tests/test_anthropic_spend.py",
    "infra/ansible/tests/test_anthropic_issuance.py",
    "infra/ansible/tests/test_anthropic_wif_admin.py",
    "infra/ansible/tests/test_child_launcher.py",
    "infra/ansible/tests/test_cloud_init_bootstrap.py",
    "infra/ansible/tests/test_dashboard_checkout.py",
    "infra/ansible/tests/test_log_secret_scan.py",
    "infra/ansible/tests/test_preview_capability_deployment.py",
    "infra/ansible/tests/test_replace_worker.py",
    "infra/ansible/tests/test_session14_qualification.py",
    "infra/ansible/tests/test_session15_proposer.py",
    "infra/ansible/tests/test_session16_cutover.py",
)
INFRA_CHECKERS = (
    "check-stack.py",
    "check-independence.py",
    "check-worker-runtime.py",
    "check-worker-qualification.py",
    "check-anthropic-spend.py",
    "check-anthropic-issuance.py",
    "check-preview-runtime.py",
)
PROTECTED_MODULE_FILES = {
    "_hashlib.py",
    "ast.py",
    "copy.py",
    "datetime.py",
    "decimal.py",
    "hashlib.py",
    "importlib.py",
    "json.py",
    "os.py",
    "pathlib.py",
    "re.py",
    "shlex.py",
    "shutil.py",
    "subprocess.py",
    "sys.py",
    "sysconfig.py",
    "tempfile.py",
    "typing.py",
    "unittest.py",
    "yaml.py",
}
STDLIB_MODULES = (hashlib, importlib, re, sysconfig)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def isolation_errors() -> list[str]:
    errors: list[str] = []
    if not sys.flags.isolated:
        errors.append("A101 readiness trust root requires python3 -I")

    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in STDLIB_MODULES:
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                f"A101 readiness trust root rejected {module.__name__} provenance: "
                f"{source!r}"
            )

    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(f"A101 readiness trust root has repository import path: {entry}")
    return errors


def workflow_step(workflow: str, name: str) -> str | None:
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n(?P<body>.*?)(?=^      - name:|\Z)",
        workflow,
    )
    return None if match is None else match.group("body")


def validate() -> list[str]:
    errors = isolation_errors()
    for relative, expected in BOUND_SOURCES.items():
        path = REPO / relative
        if not path.is_file():
            errors.append(f"bound A101 source is missing: {relative}")
            continue
        if path.is_symlink():
            errors.append(f"bound A101 source is a symlink: {relative}")
            continue
        actual = digest(path)
        if actual != expected:
            errors.append(
                f"bound A101 source differs: {relative} "
                f"(expected {expected}, observed {actual})"
            )

    expected_tests = set(EXPECTED_TEST_FILES)
    observed_infra_python = {
        str(path.relative_to(REPO))
        for path in (REPO / "infra").rglob("*.py")
        if path.is_file()
    }
    for missing in sorted(expected_tests - observed_infra_python):
        errors.append(f"explicit Ansible test census is missing: {missing}")
    for unexpected in sorted(observed_infra_python - expected_tests):
        errors.append(f"unexpected infrastructure Python source: {unexpected}")

    for path in REPO.rglob("__init__.py"):
        if path.is_file():
            errors.append(
                "repository package initializer is forbidden: "
                f"{path.relative_to(REPO)}"
            )
    for path in REPO.rglob("*.py"):
        if path.is_file() and path.name in PROTECTED_MODULE_FILES:
            errors.append(
                "repository shadows a protected Python module: "
                f"{path.relative_to(REPO)}"
            )

    wrapper_path = REPO / "tools/check-ansible.sh"
    if wrapper_path.is_file():
        wrapper = wrapper_path.read_text()
        file_block_match = re.search(
            r"(?ms)^TEST_FILES=\(\n(?P<body>.*?)^\)\n",
            wrapper,
        )
        if file_block_match is None:
            errors.append("Ansible wrapper has no explicit TEST_FILES census")
        else:
            observed_files = tuple(
                line.strip()
                for line in file_block_match.group("body").splitlines()
                if line.strip()
            )
            if observed_files != EXPECTED_TEST_FILES:
                errors.append("Ansible wrapper TEST_FILES census differs")
        if wrapper.count(
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-spend.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks one isolated spend-checker process")
        if wrapper.count(
            'python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"'
        ) != 2:
            errors.append("Ansible wrapper lacks two isolated trust-root checks")
        if wrapper.count(
            'run_gate python3 -I "$REPO_ROOT/tools/run-isolated-unittest.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks its isolated file runner")
        if "unittest discover" in wrapper or "-m unittest" in wrapper:
            errors.append("Ansible wrapper still imports tests as repository packages")

    infra_wrapper_path = REPO / "tools/check-infra.sh"
    if infra_wrapper_path.is_file():
        infra_wrapper = infra_wrapper_path.read_text()
        if infra_wrapper.count(
            'python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"'
        ) != 1:
            errors.append("infrastructure wrapper lacks its isolated trust-root check")
        for checker in INFRA_CHECKERS:
            invocation = f'run_gate python3 -I "$REPO_ROOT/tools/{checker}"'
            if infra_wrapper.count(invocation) != 1:
                errors.append(
                    f"infrastructure wrapper lacks one isolated aggregate call: {checker}"
                )
        spend_call = 'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-spend.py"'
        issuance_call = (
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-issuance.py"'
        )
        preview_call = 'run_gate python3 -I "$REPO_ROOT/tools/check-preview-runtime.py"'
        try:
            spend_index = infra_wrapper.index(spend_call)
            issuance_index = infra_wrapper.index(issuance_call)
            preview_index = infra_wrapper.index(preview_call)
        except ValueError:
            errors.append("infrastructure wrapper lacks a required Anthropic/preview checker")
        else:
            if not spend_index < issuance_index < preview_index:
                errors.append("infrastructure aggregate checker ordering differs")
        if infra_wrapper.splitlines()[-1:] != ['exit "$gate_status"']:
            errors.append("infrastructure wrapper does not preserve aggregate failure")

    for relative in (
        "tools/check-infra.sh",
        "tools/check-ansible.sh",
        "tools/install-shellcheck.sh",
    ):
        path = REPO / relative
        if path.is_file() and "source \"$REPO_ROOT/infra/tool-versions.env\"" in path.read_text():
            errors.append(f"{relative} executes infrastructure tool-version data")
        if path.is_file() and re.search(
            r'(?m)^\s*python3\s+"\$REPO_ROOT/tools/(?:check-|read-infra)',
            path.read_text(),
        ):
            errors.append(f"{relative} contains a non-isolated Python gate")

    install = REPO / "tools/install-shellcheck.sh"
    if install.is_file() and install.read_text().count(
        'python3 -I "$REPO_ROOT/tools/read-infra-tool-version.py"'
    ) != 3:
        errors.append("ShellCheck installer does not isolate all three pin reads")
    qualify = REPO / "infra/ansible/qualify.sh"
    if qualify.is_file() and qualify.read_text().count(
        'python3 -I "$REPO_ROOT/tools/check-independence.py"'
    ) != 1:
        errors.append("live qualifier does not isolate its independence checker")

    if WORKFLOW.is_file():
        workflow = WORKFLOW.read_text()
        root_digest = digest(Path(__file__))
        pin = f"{root_digest}  tools/check-a101-readiness-root.py"
        if workflow.count(pin) != 1:
            errors.append("infrastructure workflow does not pin this trust-root checker")
        root_step = workflow_step(workflow, "Verify A101 readiness trust root")
        infra_step = workflow_step(workflow, "Validate OpenTofu and stack doctrine")
        ansible_step = workflow_step(workflow, "Lint and syntax-check Ansible")
        if root_step is None:
            errors.append("infrastructure workflow lacks the A101 trust-root stage")
        elif root_step.count("python3 -I tools/check-a101-readiness-root.py") != 1:
            errors.append("workflow trust-root execution is not isolated")
        if infra_step is None or infra_step.count("run: tools/check-infra.sh") != 1:
            errors.append("workflow lacks the retained infrastructure gate")
        elif "continue-on-error" in infra_step:
            errors.append("infrastructure workflow masks the infrastructure failure")
        if ansible_step is None:
            errors.append("workflow lacks the Ansible gate")
        else:
            if ansible_step.count("        if: ${{ always() }}") != 1:
                errors.append("Ansible step does not run after infrastructure failure")
            if ansible_step.count("run: tools/check-ansible.sh") != 1:
                errors.append("workflow Ansible gate invocation differs")
        try:
            trust_index = workflow.index("Verify A101 readiness trust root")
            install_index = workflow.index("Install pinned OpenTofu")
        except ValueError:
            errors.append("infrastructure workflow lacks trust-root ordering anchors")
        else:
            if trust_index >= install_index:
                errors.append("workflow trust-root check occurs after executable setup")
    else:
        errors.append("infrastructure workflow is missing")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("A101 readiness trust root: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print("A101 readiness trust root: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
