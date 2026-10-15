import unittest

from releaseguard.cluster import CommandError, verify_ownership, verify_target


class TargetTests(unittest.TestCase):
    def test_same_name_does_not_imply_ownership(self):
        verify_ownership({"cluster": "releaseguard", "container_id": "owned"}, "owned")
        for record in [
            {},
            {"cluster": "releaseguard", "container_id": "different"},
            {"cluster": "other", "container_id": "owned"},
        ]:
            with self.assertRaises(CommandError):
                verify_ownership(record, "owned")

    def test_exact_local_target_only(self):
        args = [
            "kind-releaseguard",
            "https://127.0.0.1:41443",
            "unix:///var/run/docker.sock",
            ["releaseguard"],
            {
                "io.x-k8s.kind.cluster": "releaseguard",
                "io.x-k8s.kind.role": "control-plane",
            },
            "127.0.0.1:41443",
        ]
        self.assertEqual(verify_target(*args)["container"], "releaseguard-control-plane")
        for index, value in [
            (0, "production"),
            (1, "https://remote.example:41443"),
            (2, "tcp://remote:2376"),
            (3, ["other"]),
            (4, {"io.x-k8s.kind.cluster": "other"}),
            (5, "127.0.0.1:42443"),
        ]:
            changed = args.copy()
            changed[index] = value
            with self.assertRaises(CommandError):
                verify_target(*changed)
