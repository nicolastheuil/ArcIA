import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harness", ROOT / "scripts/harness.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "examples/synthetic/instance.json").read_text())
        self.lock = json.loads((ROOT / "versions.lock.yaml").read_text())

    def reject(self, code):
        with self.assertRaisesRegex(harness.Invalid, "^" + code + "$"):
            harness.validate(self.config)

    def test_valid_fixture(self):
        self.assertIs(harness.validate(self.config), self.config)

    def test_requires_three_servers(self):
        self.config["nodes"].pop()
        self.reject("THREE_SERVERS")

    def test_no_duplicate_addresses(self):
        self.config["nodes"][1]["address"] = self.config["nodes"][0]["address"]
        self.reject("DUPLICATE_NODE")

    def test_no_duplicate_names(self):
        self.config["nodes"][1]["name"] = self.config["nodes"][0]["name"]
        self.reject("DUPLICATE_NODE")

    def test_no_podspec_in_config(self):
        self.config["podSpec"] = {"hostNetwork": True}
        self.reject("CONFIG_FIELDS")

    def test_no_secret_in_node(self):
        self.config["nodes"][0]["password"] = "SYNTHETIC_SECRET"
        self.reject("NODE_FIELDS")

    def test_no_placeholder(self):
        self.config["nodes"][0]["identity_file"] = "<KEY>"
        self.reject("SSH_FILE_REFERENCE")

    def test_no_shell_in_identity(self):
        self.config["nodes"][0]["ssh_user"] = "engineer;whoami"
        self.reject("SSH_USER")

    def test_no_public_repository(self):
        self.config["github"]["visibility"] = "public"
        self.reject("PRIVATE_REQUIRED")

    def test_no_bool_ssh_port(self):
        self.config["nodes"][0]["ssh_port"] = True
        self.reject("SSH_PORT")

    def test_no_overlap_pod_service(self):
        self.config["network"]["service_cidr"] = "10.42.1.0/24"
        self.reject("CIDR_OVERLAP")

    def test_no_overlap_company_or_vpn(self):
        self.config["network"]["existing_cidrs"].append("10.0.0.0/8")
        self.reject("CIDR_OVERLAP")

    def test_no_node_inside_pod_network(self):
        self.config["nodes"][0]["address"] = "10.42.0.11"
        self.reject("NODE_CIDR_OVERLAP")

    def test_no_single_node_api_endpoint(self):
        self.config["network"]["api_endpoint"] = self.config["nodes"][0]["name"]
        self.reject("STABLE_API_REQUIRED")

    def test_fixture_cannot_become_real_without_real_endpoints(self):
        self.config["synthetic"] = False
        for i, node in enumerate(self.config["nodes"]):
            node["address"] = "10.8.0." + str(i + 11)
        self.reject("REAL_ENDPOINT_REQUIRED")

    def test_production_requires_rfc1918(self):
        self.config["synthetic"] = False
        self.config["nodes"][0]["address"] = "8.8.8.8"
        self.reject("PRIVATE_NODES_REQUIRED")

    def test_plan_remains_closed_and_does_not_expose_token(self):
        p = harness.plan(self.config, self.lock)
        self.assertFalse(p["installation_ready"])
        self.assertFalse(p["release_ready"])
        self.assertIn("CPI_DIGEST_PENDING", p["blockers"])
        self.assertNotIn("192.0.2", json.dumps(p))

    def test_render_has_one_initial_server_and_common_parameters(self):
        inv = harness.render(self.config, "a" * 64, self.lock)
        configs = [h["hermes_k3s_config"] for h in inv["all"]["children"]["k3s_servers"]["hosts"].values()]
        self.assertEqual(sum(c.get("cluster-init", False) for c in configs), 1)
        for c in configs:
            self.assertTrue(c["secrets-encryption"])
            self.assertEqual(c["write-kubeconfig-mode"], "0600")
            self.assertIn("local-storage", c["disable"])
            self.assertNotIn("token", c)
            self.assertNotIn("disable-network-policy", c)
        for k in ("cluster-cidr", "service-cidr", "tls-san", "disable", "flannel-backend", "kubelet-arg"):
            self.assertTrue(all(c[k] == configs[0][k] for c in configs))

    def test_bad_token_rejected(self):
        with self.assertRaisesRegex(harness.Invalid, "TOKEN_FORMAT"):
            harness.render(self.config, "short", self.lock)

    def test_windows_paths_render_for_wsl_without_copying_keys(self):
        self.assertEqual(harness.controller_path(r"C:\Users\Engineer\a key"), "/mnt/c/Users/Engineer/a key")
        self.assertEqual(harness.controller_path("/protected/key"), "/protected/key")

    def test_invalid_cpi_digest_does_not_open_gate(self):
        self.lock["components"]["vsphere_cpi"]["image_digest"] = "latest"
        self.assertIn("CPI_DIGEST_PENDING", harness.installation_blockers(self.config, self.lock))

    def test_render_cli_keeps_token_out_of_output(self):
        with tempfile.TemporaryDirectory() as directory:
            p = subprocess.run([sys.executable, str(ROOT / "scripts/harness.py"), "render", "--stdin",
                                "--output-dir", directory], input=json.dumps({"config": self.config,
                                "k3s_token": "f" * 64}).encode(), capture_output=True)
            self.assertEqual(p.returncode, 0)
            self.assertNotIn(b"f" * 64, p.stdout + p.stderr)
            self.assertTrue((Path(directory) / "inventory.private.json").is_file())

    def test_synthetic_target_never_contacts_ssh(self):
        with patch.object(harness.subprocess, "run") as run:
            with self.assertRaisesRegex(harness.Invalid, "SYNTHETIC_TARGET"):
                harness.remote_preflight(self.config)
            run.assert_not_called()

    def test_ssh_facts_sanitized_and_clone_detected(self):
        self.config["synthetic"] = False
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / "key"
            identity.write_text("synthetic")
            for node in self.config["nodes"]:
                node["identity_file"] = node["known_hosts_file"] = str(identity)
            raw = json.dumps({"checks": {"debian_13": True}, "machine_id": "PRIVATE_MACHINE_ID",
                              "product_uuid": "PRIVATE_VM_UUID"}).encode()
            completed = subprocess.CompletedProcess([], 0, stdout=raw, stderr=b"PRIVATE_STDERR")
            with patch.object(harness.subprocess, "run", return_value=completed) as run:
                result = harness.remote_preflight(self.config)
            self.assertFalse(result["passed"])
            self.assertFalse(result["nodes"][1]["checks"]["machine_id_unique"])
            self.assertNotIn("PRIVATE_", json.dumps(result))
            command = run.call_args.args[0]
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertIn("BatchMode=yes", command)
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_cli_error_does_not_print_private_value(self):
        self.config["secret-canary"] = "CANARY_NEVER_PRINT"
        p = subprocess.run([sys.executable, str(ROOT / "scripts/harness.py"), "validate", "--stdin"],
                           input=json.dumps({"config": self.config}).encode(), capture_output=True)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn(b"CANARY_NEVER_PRINT", p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["code"], "CONFIG_FIELDS")

    def test_cli_rejects_output_inside_repo_before_writing(self):
        p = subprocess.run([sys.executable, str(ROOT / "scripts/harness.py"), "render", "--stdin",
                            "--output-dir", str(ROOT / "private")], input=json.dumps({"config": self.config,
                            "k3s_token": "a" * 64}).encode(), capture_output=True)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["code"], "OUTPUT_INSIDE_REPO")

    def test_k3s_immutable_artifacts(self):
        c = self.lock["components"]["k3s"]
        self.assertIn(c["revision"], c["installer_url"])
        for k in ("installer_sha256", "binary_sha256", "images_sha256"):
            self.assertRegex(c[k], r"^[a-f0-9]{64}$")
        self.assertNotIn("latest", json.dumps(self.lock))

    def test_foundation_is_closed_and_has_no_business_workload(self):
        resources = json.loads((ROOT / "deploy/foundation/resources.yaml").read_text())["items"]
        namespaces = [r for r in resources if r["kind"] == "Namespace"]
        self.assertEqual(len(namespaces), 5)
        for ns in namespaces:
            self.assertEqual(ns["metadata"]["labels"]["pod-security.kubernetes.io/enforce"], "restricted")
            policies = [r for r in resources if r["kind"] == "NetworkPolicy" and
                        r["metadata"]["namespace"] == ns["metadata"]["name"] and
                        r["metadata"]["name"] == "default-deny-all"]
            self.assertEqual(len(policies), 1)
            self.assertEqual(set(policies[0]["spec"]["policyTypes"]), {"Ingress", "Egress"})
            self.assertNotIn("ingress", policies[0]["spec"])
            self.assertNotIn("egress", policies[0]["spec"])
        self.assertFalse(any(r["kind"] in ("Deployment", "StatefulSet", "ClusterRoleBinding", "Ingress") for r in resources))
        self.assertTrue(all(r["automountServiceAccountToken"] is False for r in resources if r["kind"] == "ServiceAccount"))


if __name__ == "__main__":
    unittest.main()
