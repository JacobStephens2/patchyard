import hashlib
import pathlib
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "tools/anthropic-wif-admin.py"
EXPECTED_ADMIN_SOURCE_SHA256 = (
    "89794bd6235d5b37dfa4999a792588396ece9935b17820954b75d8b055822c91"
)


def load_exact_source_module(name: str, path: pathlib.Path, expected: str) -> types.ModuleType:
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != expected:
        raise RuntimeError(f"{path.name} differs from its exact source binding")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


ADMIN = load_exact_source_module(
    "anthropic_wif_admin", MODULE_PATH, EXPECTED_ADMIN_SOURCE_SHA256
)


class FakeAdmin:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.paths = []

    def list_all(self, path):
        self.paths.append(path)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class AnthropicWifAdminContract(unittest.TestCase):
    @mock.patch.object(ADMIN.time, "sleep")
    def test_new_account_membership_retries_provider_404(self, sleep):
        api = FakeAdmin(
            [
                ADMIN.ApiError("not propagated", status_code=404),
                ADMIN.ApiError("still propagating", status_code=404),
                [{"workspace_id": "wrkspc_example"}],
            ]
        )

        result = ADMIN.list_memberships(
            api, "/v1/organizations/service_accounts/svac_example/workspaces",
            retry_not_found=True,
        )

        self.assertEqual(result, [{"workspace_id": "wrkspc_example"}])
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2)])
        self.assertEqual(len(api.paths), 3)

    @mock.patch.object(ADMIN.time, "sleep")
    def test_existing_account_does_not_mask_not_found(self, sleep):
        error = ADMIN.ApiError("missing", status_code=404)
        api = FakeAdmin([error])

        with self.assertRaises(ADMIN.ApiError) as observed:
            ADMIN.list_memberships(
                api, "/v1/organizations/service_accounts/svac_example/workspaces",
                retry_not_found=False,
            )

        self.assertIs(observed.exception, error)
        sleep.assert_not_called()

    @mock.patch.object(ADMIN.time, "sleep")
    def test_new_account_does_not_retry_other_failures(self, sleep):
        error = ADMIN.ApiError("forbidden", status_code=403)
        api = FakeAdmin([error])

        with self.assertRaises(ADMIN.ApiError) as observed:
            ADMIN.list_memberships(
                api, "/v1/organizations/service_accounts/svac_example/workspaces",
                retry_not_found=True,
            )

        self.assertIs(observed.exception, error)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
