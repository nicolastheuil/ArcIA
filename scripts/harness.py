#!/usr/bin/env python3
"""Preparation CLI. Never emits private config, subprocess output or exception text."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GATES = ("vmware_compatibility", "api_failover", "network_review", "cpi_design")


class Invalid(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Invalid(code)


def keys(value, expected, code):
    require(isinstance(value, dict) and set(value) == set(expected), code)


def text_value(value):
    return isinstance(value, str) and bool(value.strip()) and not re.search(
        r"[<>\r\n\x00]|CHANGEME|TODO|REPLACE", value, re.I)


def hostname(value):
    return isinstance(value, str) and len(value) <= 253 and all(
        re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", p)
        for p in value.split("."))


def validate(config):
    required={"schema_version", "synthetic", "github", "nodes", "network", "storage", "gates"}
    require(isinstance(config,dict) and set(config) in (required,required|{'identity'}),'CONFIG_FIELDS')
    if 'identity' in config:
        require(isinstance(config['identity'], dict) and
                set(config['identity']) in ({'personal_slots'}, {'personal_slots', 'https_egress_mode'}),
                'IDENTITY_FIELDS')
        require(type(config['identity']['personal_slots']) is int and 1<=config['identity']['personal_slots']<=32,
                'PERSONAL_RUNTIME_CAPACITY_INVALID')
        require(config['identity'].get('https_egress_mode', 'disabled') in ('disabled', 'public_ipv4_443'),
                'IDENTITY_HTTPS_EGRESS_MODE_INVALID')
    require(type(config["schema_version"]) is int and config["schema_version"] == 1,
            "SCHEMA_VERSION")
    require(type(config["synthetic"]) is bool, "SYNTHETIC_FLAG")
    keys(config["github"], ("account", "repository", "visibility"), "GITHUB_FIELDS")
    gh = config["github"]
    require(isinstance(gh["account"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", gh["account"]), "GITHUB_ACCOUNT")
    require(isinstance(gh["repository"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", gh["repository"]), "GITHUB_REPO")
    require(gh["visibility"] == "private", "PRIVATE_REQUIRED")
    require(isinstance(config["nodes"], list) and len(config["nodes"]) == 3, "THREE_SERVERS")
    seen = {k: set() for k in ("name", "address")}
    for node in config["nodes"]:
        keys(node, ("name", "address", "ssh_user", "ssh_port", "identity_file",
                    "known_hosts_file"), "NODE_FIELDS")
        require(hostname(node["name"]), "NODE_NAME")
        address = ipaddress.ip_address(node["address"])
        require(address.version == 4 and not address.is_loopback and not address.is_multicast
                and not address.is_unspecified, "NODE_ADDRESS")
        require(config["synthetic"] or any(address in ipaddress.ip_network(cidr) for cidr in
                ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")), "PRIVATE_NODES_REQUIRED")
        require(isinstance(node["ssh_user"], str) and re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", node["ssh_user"]), "SSH_USER")
        require(type(node["ssh_port"]) is int and 1 <= node["ssh_port"] <= 65535, "SSH_PORT")
        require(all(text_value(node[k]) for k in ("identity_file", "known_hosts_file")), "SSH_FILE_REFERENCE")
        for k in seen:
            require(node[k] not in seen[k], "DUPLICATE_NODE")
            seen[k].add(node[k])
    keys(config["network"], ("api_endpoint", "public_hostname", "pod_cidr", "service_cidr",
                             "existing_cidrs", "existing_cidrs_reviewed"), "NETWORK_FIELDS")
    net = config["network"]
    require(hostname(net["api_endpoint"]) and hostname(net["public_hostname"]), "ENDPOINT_HOSTNAME")
    require(config["synthetic"] or not any(net[k].endswith((".invalid", ".example"))
            for k in ("api_endpoint", "public_hostname")), "REAL_ENDPOINT_REQUIRED")
    require(net["api_endpoint"] not in seen["address"] | seen["name"], "STABLE_API_REQUIRED")
    require(type(net["existing_cidrs_reviewed"]) is bool, "NETWORK_REVIEW_FLAG")
    require(isinstance(net["existing_cidrs"], list), "EXISTING_NETWORKS")
    pools = [ipaddress.ip_network(net[k], strict=True) for k in ("pod_cidr", "service_cidr")]
    require(all(p.version == 4 and p.is_private for p in pools), "PRIVATE_CIDRS")
    require(pools[0].prefixlen <= 24 and pools[1].prefixlen <= 24, "CIDR_CAPACITY")
    existing = [ipaddress.ip_network(p, strict=True) for p in net["existing_cidrs"]]
    require(not pools[0].overlaps(pools[1]), "CIDR_OVERLAP")
    for pool in pools:
        require(not any(pool.version == p.version and pool.overlaps(p) for p in existing), "CIDR_OVERLAP")
        require(not any(ipaddress.ip_address(n["address"]) in pool for n in config["nodes"]), "NODE_CIDR_OVERLAP")
    keys(config["storage"], ("storage_class", "policy_ref"), "STORAGE_FIELDS")
    require(hostname(config["storage"]["storage_class"]) and text_value(config["storage"]["policy_ref"]), "STORAGE_REQUIRED")
    keys(config["gates"], GATES, "GATE_FIELDS")
    require(all(v in ("pending", "verified") for v in config["gates"].values()), "GATE_STATE")
    return config


def installation_blockers(config, lock):
    blockers = ["GATE_" + g.upper() for g in GATES if config["gates"][g] != "verified"]
    if config["synthetic"]:
        blockers.append("SYNTHETIC_TARGET")
    if not config["network"]["existing_cidrs_reviewed"]:
        blockers.append("NETWORK_INVENTORY_PENDING")
    if lock["components"]["k3s"]["status"] not in ("source_verified_not_qualified", "qualified"):
        blockers.append("K3S_SOURCE_PENDING")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", lock["components"]["vsphere_cpi"].get("image_digest") or ""):
        blockers.append("CPI_DIGEST_PENDING")
    return blockers


def plan(config, lock):
    return {"status": "prepared", "server_count": 3, "safe_mode": True,
            "installation_ready": not installation_blockers(config, lock),
            "blockers": installation_blockers(config, lock), "deployed": False,
            "release_ready": False}


def render(config, token, lock):
    validate(config)
    require(isinstance(token, str) and re.fullmatch(r"[a-f0-9]{64}", token), "TOKEN_FORMAT")
    hosts = {}
    for index, node in enumerate(config["nodes"]):
        k3s = {
            "node-name": node["name"], "node-ip": node["address"],
            "write-kubeconfig-mode": "0600", "secrets-encryption": True,
            "token-file": "/etc/rancher/k3s/cluster-token",
            "tls-san": [config["network"]["api_endpoint"]],
            "cluster-cidr": config["network"]["pod_cidr"],
            "service-cidr": config["network"]["service_cidr"],
            "flannel-backend": "vxlan",
            "disable": ["traefik", "servicelb", "local-storage"],
            "disable-cloud-controller": True,
            "kubelet-arg": ["cloud-provider=external"],
            "etcd-snapshot-retention": 14,
            "etcd-snapshot-schedule-cron": "0 * * * *",
        }
        if index == 0:
            k3s["cluster-init"] = True
        else:
            k3s["server"] = "https://" + config["network"]["api_endpoint"] + ":6443"
        hosts[node["name"]] = {
            "ansible_host": node["address"], "ansible_user": node["ssh_user"],
            "ansible_port": node["ssh_port"],
            "ansible_ssh_private_key_file": controller_path(node["identity_file"]),
            "ansible_ssh_common_args": "-o StrictHostKeyChecking=yes -o UserKnownHostsFile=" +
                "'" + controller_path(node["known_hosts_file"]).replace("'", "'\"'\"'") + "'",
            "hermes_k3s_config": k3s,
        }
    inventory = {"all": {"children": {"k3s_servers": {"hosts": hosts}}, "vars": {
        "ansible_python_interpreter": "/usr/bin/python3",
        "hermes_k3s_token": token,
        "hermes_installation_ready": not installation_blockers(config, lock),
        "hermes_safe_mode": True,
        "hermes_api_endpoint": config["network"]["api_endpoint"],
        "hermes_lock": lock,
    }}}
    return inventory


def controller_path(value):
    """A Windows drive path maps to the same engineer's WSL mount; never copy keys."""
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return "/mnt/" + value[0].lower() + "/" + value[3:].replace("\\", "/")
    return value


def doctor():
    statuses = {name: bool(shutil.which(name)) for name in
                ("git", "ssh", "gh", "ansible-playbook", "kubectl", "helm", "age", "sops")}
    auth = False
    if statuses["gh"]:
        auth = subprocess.run(["gh", "auth", "status"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=20).returncode == 0
    return {"tools": statuses, "github_authenticated": auth, "deployed": False}


def remote_preflight(config):
    """Read-only sudo probe. Raw results stay inside this process."""
    require(not config["synthetic"], "SYNTHETIC_TARGET")
    probe = (ROOT / "scripts" / "node_probe.py").read_bytes()
    results, identifiers = [], {"machine_id": set(), "product_uuid": set()}
    for i, node in enumerate(config["nodes"], 1):
        require(all(Path(node[k]).is_file() for k in ("identity_file", "known_hosts_file")), "SSH_FILES_MISSING")
        cmd = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=10", "-o", "IdentitiesOnly=yes",
               "-o", "UserKnownHostsFile=" + node["known_hosts_file"],
               "-i", node["identity_file"], "-p", str(node["ssh_port"]),
               node["ssh_user"] + "@" + node["address"], "sudo -n python3 -"]
        try:
            p = subprocess.run(cmd, input=probe, capture_output=True, timeout=45)
            require(p.returncode == 0 and len(p.stdout) < 16384, "SSH_OR_SUDO_FAILED")
            raw = json.loads(p.stdout)
            checks = raw["checks"]
            require(isinstance(checks, dict) and all(type(v) is bool for v in checks.values()), "PROBE_FORMAT")
            for key in identifiers:
                value = raw[key]
                checks[key + "_unique"] = bool(value) and value not in identifiers[key]
                identifiers[key].add(value)
            results.append({"node": "N" + str(i), "checks": checks, "passed": all(checks.values())})
        except (Invalid, ValueError, KeyError, subprocess.SubprocessError):
            results.append({"node": "N" + str(i), "passed": False, "error": "PREFLIGHT_FAILED"})
    return {"nodes": results, "passed": all(r["passed"] for r in results),
            "vmware_csi_qualified": False, "endpoint_failover_qualified": False}


def main():
    parser = argparse.ArgumentParser(description="ArcIA harness: preparation only")
    parser.add_argument("command", choices=("doctor", "validate", "plan", "render", "preflight"))
    parser.add_argument("--stdin", action="store_true", help="Read protected bundle from stdin")
    parser.add_argument("--config", type=Path, help="Synthetic fixture only")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = doctor()
        else:
            require(args.stdin != bool(args.config), "ONE_INPUT_REQUIRED")
            bundle = json.load(sys.stdin) if args.stdin else {"config": json.loads(args.config.read_text(encoding="utf-8"))}
            config = validate(bundle["config"])
            require(args.stdin or config["synthetic"], "PRIVATE_INPUT_REQUIRES_STDIN")
            lock = json.loads((ROOT / "versions.lock.yaml").read_text(encoding="utf-8"))
            if args.command == "validate":
                result = {"valid": True}
            elif args.command == "plan":
                result = plan(config, lock)
            elif args.command == "preflight":
                result = remote_preflight(config)
            else:
                require(args.stdin and args.output_dir is not None, "PROTECTED_OUTPUT_REQUIRED")
                output = args.output_dir.resolve()
                require(not output.is_relative_to(ROOT), "OUTPUT_INSIDE_REPO")
                require(output.is_dir() and not any(output.iterdir()), "EMPTY_PROTECTED_OUTPUT_REQUIRED")
                value = render(config, bundle["k3s_token"], lock)
                path = output / "inventory.private.json"
                with path.open("x", encoding="utf-8") as stream:
                    json.dump(value, stream, indent=2)
                if os.name != "nt":
                    path.chmod(0o600)
                result = plan(config, lock)
                result["rendered"] = True
        print(json.dumps(result, indent=2))
        return 2 if result.get("passed") is False else 0
    except Invalid as exc:
        print(json.dumps({"status": "blocked", "code": str(exc)}))
        return 2
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print(json.dumps({"status": "blocked", "code": "INVALID_INPUT_OR_LOCAL_FAILURE"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
