import unittest
from unittest.mock import patch

from releaseguard.cluster import CommandError, guard_docker_environment


class DockerEnvironmentTests(unittest.TestCase):
    def test_remote_override_is_rejected_before_any_command(self):
        with (
            patch.dict("os.environ", {"DOCKER_HOST": "tcp://example.invalid:2375"}),
            self.assertRaises(CommandError),
        ):
            guard_docker_environment()
        with patch.dict("os.environ", {"DOCKER_HOST": "unix:///var/run/docker.sock"}):
            guard_docker_environment()
