import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "infra/ansible/roles/control_plane"
LAUNCHER = CONTROL / "files/patchyard-child-launcher"
SUPERVISOR_UNIT = CONTROL / "files/factory-supervisor.service"
TASKS = CONTROL / "tasks/main.yml"
ENVIRONMENT = CONTROL / "templates/patchyard-supervisor.env.j2"
RUNTIME = ROOT / "policy/proposer-runtime.json"
ROUTING = ROOT / "policy/routing.json"


class Session15ProposerContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LAUNCHER.read_text()
        cls.unit = SUPERVISOR_UNIT.read_text()
        cls.tasks = TASKS.read_text()
        cls.environment = ENVIRONMENT.read_text()
        cls.runtime = json.loads(RUNTIME.read_text())
        cls.routing = json.loads(ROUTING.read_text())

    def test_proposer_child_is_offline_and_receives_only_typed_inputs(self) -> None:
        section = self.launcher.split('if [[ "$KIND" == proposer || "$KIND" == proposer_disposition ]]; then', 1)[1]
        section = section.split('if [[ "$KIND" == review ]]; then', 1)[0]
        self.assertIn('--unshare-net', self.launcher)
        self.assertIn('"${BWRAP_BASE[@]}"', section)
        self.assertIn('"$JOB/input/packet.json"', section)
        self.assertIn('"$JOB/input/prompt.md"', section)
        self.assertIn('/opt/patchyard/fixtures/pipeline/bin/proposer-stub', section)
        self.assertIn('/opt/patchyard/fixtures/pipeline/bin/disposition-stub', section)
        self.assertIn('offline-proposer', section)
        self.assertIn('offline-proposer-disposition', section)
        self.assertNotIn('DATABASE_URL', section)
        self.assertNotIn('/opt/patchyard /workspace', section)
        self.assertNotIn('/var/lib/patchyard', section)

    def test_schedule_is_installed_dormant_until_live_provider_qualification(self) -> None:
        self.assertIn('FACTORY_PROPOSER_ENABLED=false', self.environment)
        self.assertIn('FACTORY_PROPOSER_DUAL_REVIEW_ENFORCED=false', self.environment)
        self.assertIn('FACTORY_PROPOSER_INTERVAL_SECONDS=86400', self.environment)
        self.assertIn(
            'FACTORY_PROPOSER_BASE_SHA={{ factory_repo_revision }}',
            self.environment,
        )
        self.assertFalse(self.routing['live_provider_execution'])

    def test_ideas_projection_is_private_append_state_not_the_installed_repo(self) -> None:
        self.assertIn(
            'path: /var/lib/patchyard/proposer-inbox/docs', self.tasks
        )
        self.assertIn(
            'dest: /var/lib/patchyard/proposer-inbox/docs/ideas.md', self.tasks
        )
        self.assertIn('force: false', self.tasks)
        self.assertIn(
            'FACTORY_PROPOSER_IDEAS_PATH=/var/lib/patchyard/proposer-inbox/docs/ideas.md',
            self.environment,
        )
        self.assertIn('ProtectSystem=strict', self.unit)
        self.assertIn('ReadWritePaths=/var/lib/patchyard ', self.unit)

    def test_prompt_include_graph_is_closed_and_base_pinned(self) -> None:
        roots = set(self.runtime['author_roots']) | set(
            self.runtime['reviewer_roots']
        )
        includes = self.runtime['includes']
        self.assertTrue(roots <= set(includes))
        for targets in includes.values():
            self.assertTrue(set(targets) <= set(includes))
        self.assertIn('policy/proposer.md', self.runtime['author_roots'])
        self.assertIn('policy/proposer-runtime.json', self.runtime['author_roots'])
        self.assertIn('policy/proposer-runtime.json', self.runtime['reviewer_roots'])

    def test_author_and_policy_reviewer_are_cross_family(self) -> None:
        proposer = self.routing['rules']['improvement_proposer']
        reviewer_name = proposer['reviewers'][0]
        reviewer = self.routing['rules'][reviewer_name]
        self.assertEqual(reviewer_name, 'improvement_proposer_review')
        self.assertNotEqual(
            proposer['seat']['provider'], reviewer['seat']['provider']
        )
        self.assertNotEqual(
            proposer['seat']['harness'], reviewer['seat']['harness']
        )


if __name__ == '__main__':
    unittest.main()
