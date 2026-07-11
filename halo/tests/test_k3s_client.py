#!/usr/bin/env python3
"""Unit tests for halo.common.k3s_client (mocked)."""

import json
import unittest
from unittest.mock import patch, MagicMock
from halo.common.k3s_client import K3sClient


class TestK3sClient(unittest.TestCase):

    @patch("halo.common.k3s_client.subprocess.run")
    def test_scale_deployment(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        client = K3sClient(namespace="halo")
        client.scale_deployment("ws-demo", 1)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("kubectl", cmd)
        self.assertIn("-n", cmd)
        self.assertIn("halo", cmd)
        self.assertIn("scale", cmd)
        self.assertIn("--replicas=1", cmd)

    @patch("halo.common.k3s_client.subprocess.run")
    def test_get_deployment_status_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({
            "status": {"readyReplicas": 1},
            "spec": {"replicas": 1}
        }), stderr="")
        client = K3sClient(namespace="halo")
        status = client.get_deployment_status("ws-demo")
        self.assertTrue(status["exists"])
        self.assertTrue(status["ready"])
        self.assertEqual(status["replicas"], 1)

    @patch("halo.common.k3s_client.subprocess.run")
    def test_get_deployment_status_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        client = K3sClient(namespace="halo")
        status = client.get_deployment_status("ws-missing")
        self.assertFalse(status["exists"])

    @patch("halo.common.k3s_client.subprocess.run")
    def test_list_pods(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({
            "items": [
                {"metadata": {"name": "pod-1", "namespace": "halo"},
                 "status": {"phase": "Running"}},
                {"metadata": {"name": "pod-2", "namespace": "halo"},
                 "status": {"phase": "Pending"}},
            ]
        }), stderr="")
        client = K3sClient(namespace="halo")
        pods = client.list_pods()
        self.assertEqual(len(pods), 2)
        self.assertEqual(pods[0]["name"], "pod-1")
        self.assertEqual(pods[0]["phase"], "Running")
        self.assertEqual(pods[1]["phase"], "Pending")


if __name__ == '__main__':
    unittest.main()