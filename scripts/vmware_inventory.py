#!/usr/bin/env python3
"""Private vCenter discovery. Credentials arrive via stdin, never arguments/logs.

Successful stdout is a private response consumed by the protected local GUI.
Do not invoke this script directly from an agent tool with real configuration.
"""
import hashlib
import hmac
import json
import re
import socket
import ssl
import sys


class Invalid(ValueError):
    pass


def safe_error_code(exc):
    """Classify errors without exposing fault messages or connection values."""
    for _ in range(4):
        if isinstance(exc, Invalid):
            return str(exc)  # Only constants raised by validate_connection/read_inventory.
        if isinstance(exc, ssl.SSLCertVerificationError):
            return "TLS_TRUST_FAILED"
        if isinstance(exc, ssl.SSLError):
            return "TLS_HANDSHAKE_FAILED"
        if isinstance(exc, socket.gaierror):
            return "VCENTER_DNS_FAILED"
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return "VCENTER_TIMEOUT"
        if isinstance(exc, ConnectionError):
            return "VCENTER_NETWORK_FAILED"
        if isinstance(exc, FileNotFoundError):
            return "CA_FILE_UNREADABLE"
        if isinstance(exc, ModuleNotFoundError):
            return "SDK_RUNTIME_ERROR"
        fault = type(exc).__name__.split(".")[-1]
        if fault in ("InvalidLogin", "NotAuthenticated"):
            return "VCENTER_AUTHENTICATION_FAILED"
        if fault == "NoPermission":
            return "VCENTER_PERMISSION_DENIED"
        exc = getattr(exc, "reason", None) or getattr(exc, "__cause__", None)
        if exc is None:
            break
    return "VCENTER_CONNECTION_OR_INVENTORY_FAILED"


def validate_connection(data):
    required = {"server", "port", "username", "password", "ca_file"}
    if not isinstance(data, dict) or not required <= set(data) or set(data) - required - {"certificate_sha256"}:
        raise Invalid("CONNECTION_FIELDS")
    server = data["server"]
    if not isinstance(server, str) or len(server) > 253 or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]*", server):
        raise Invalid("SERVER_HOSTNAME_REQUIRED")
    if type(data["port"]) is not int or not 1 <= data["port"] <= 65535:
        raise Invalid("PORT_INVALID")
    if not all(isinstance(data[k], str) and data[k] and "\x00" not in data[k] for k in ("username", "password")):
        raise Invalid("CREDENTIALS_REQUIRED")
    if not isinstance(data["ca_file"], str) or "\x00" in data["ca_file"]:
        raise Invalid("CA_REFERENCE_INVALID")
    if "certificate_sha256" in data and (not isinstance(data["certificate_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", data["certificate_sha256"])):
        raise Invalid("TLS_FINGERPRINT_INVALID")
    return data


class PinnedTLSContext(ssl.SSLContext):
    """Verify the accepted certificate on EVERY socket, before any HTTP/auth."""
    def __new__(cls, fingerprint, algorithm='sha256'):
        return super().__new__(cls, ssl.PROTOCOL_TLS_CLIENT)

    def __init__(self, fingerprint, algorithm='sha256'):
        self.check_hostname = False
        self.verify_mode = ssl.CERT_NONE
        self.minimum_version = ssl.TLSVersion.TLSv1_2
        self.fingerprint = fingerprint
        self.algorithm = algorithm

    def wrap_socket(self, *args, **kwargs):
        if kwargs.get("do_handshake_on_connect", True) is not True:
            raise Invalid("TLS_HANDSHAKE_REQUIRED")
        channel = super().wrap_socket(*args, **kwargs)
        if not hmac.compare_digest(hashlib.new(self.algorithm, channel.getpeercert(binary_form=True)).hexdigest(), self.fingerprint):
            channel.close()
            raise Invalid("TLS_FINGERPRINT_CHANGED")
        return channel


def probe_certificate(connection):
    """Unauthenticated TLS only. A human must accept the result in the local UI."""
    validate_connection(connection)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection((connection["server"], connection["port"]), timeout=15) as tcp:
        with context.wrap_socket(tcp, server_hostname=connection["server"]) as channel:
            fingerprint = hashlib.sha256(channel.getpeercert(binary_form=True)).hexdigest()
    return {"status": "certificate_pending", "sha256": fingerprint, "deployed": False}


def inventory_path(obj):
    names = []
    while obj is not None:
        if getattr(obj, "name", None):
            names.append(obj.name)
        obj = getattr(obj, "parent", None)
    # vCenter's root Folder is not part of FindByInventoryPath paths.
    return "/" + "/".join(reversed(names[:-1]))


def read_inventory(connection, connect=None, disconnect=None):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    validate_connection(connection)
    # Either normal CA validation, or an explicitly accepted exact certificate.
    # No unrestricted insecure connection can reach VMware authentication.
    context = (PinnedTLSContext(connection["certificate_sha256"]) if connection.get("certificate_sha256")
               else ssl.create_default_context(cafile=connection["ca_file"] or None))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    session = (connect or SmartConnect)(host=connection["server"], port=connection["port"],
        user=connection["username"], pwd=connection["password"], sslContext=context,
        httpConnectionTimeout=30)
    view = None
    try:
        content = session.RetrieveContent()
        if content.about.apiType != "VirtualCenter":
            raise Invalid("VCENTER_REQUIRED")
        types = [vim.Datacenter, vim.ClusterComputeResource, vim.Datastore, vim.Network,
                 vim.Folder, vim.VirtualMachine]
        view = content.viewManager.CreateContainerView(content.rootFolder, types, True)
        records = {"datacenters": [], "clusters": [], "datastores": [], "networks": [],
                   "folders": [], "templates": [], "arcia_vms": []}
        for obj in view.view:
            entry = {"id": obj._moId, "name": obj.name, "path": inventory_path(obj)}
            if isinstance(obj, vim.Datacenter):
                records["datacenters"].append(entry)
            elif isinstance(obj, vim.ClusterComputeResource):
                entry["hosts"] = [{"id": h._moId, "name": h.name,
                    "connected": str(h.runtime.connectionState) == "connected",
                    "maintenance": h.runtime.inMaintenanceMode,
                    "version": h.config.product.version if h.config else None} for h in obj.host]
                records["clusters"].append(entry)
            elif isinstance(obj, vim.Datastore):
                entry.update({"accessible": obj.summary.accessible, "type": obj.summary.type,
                              "free_gib": obj.summary.freeSpace // 1024**3})
                records["datastores"].append(entry)
            elif isinstance(obj, vim.Network):
                records["networks"].append(entry)
            elif isinstance(obj, vim.Folder):
                records["folders"].append(entry)
            elif isinstance(obj, vim.VirtualMachine):
                if obj.config and obj.config.template:
                    entry["guest_id"] = obj.config.guestId
                    records["templates"].append(entry)
                elif obj.name in ("arcia-k3s-01", "arcia-k3s-02", "arcia-k3s-03"):
                    entry["power_state"] = str(obj.runtime.powerState)
                    records["arcia_vms"].append(entry)
        return {"status": "connected", "version": content.about.version,
                "build": content.about.build, "inventory": records,
                "deployed": False, "operation": "read_only_inventory"}
    finally:
        try:
            if view is not None:
                view.Destroy()
        finally:
            (disconnect or Disconnect)(session)


def main():
    try:
        data = json.load(sys.stdin)
        validate_connection(data)
        result = probe_certificate(data) if sys.argv[1:] == ["--certificate"] else read_inventory(data)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        # VMware fault messages can contain hostnames, identities and object paths.
        print(json.dumps({"status": "blocked", "code": safe_error_code(exc), "deployed": False}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
