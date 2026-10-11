#!/usr/bin/env python3
"""Prepare public Debian disk locally. No VMware connection or private input.

This produces an importable disk, not a qualified template. The generic image
contains cloud-init, but open-vm-tools must be installed during NoCloud bootstrap.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha512").hexdigest()


def verified_download(url, destination, expected):
    destination = Path(destination)
    if destination.exists():
        if destination.is_symlink() or digest(destination) != expected:
            raise ValueError("EXISTING_IMAGE_HASH_MISMATCH")
        return
    if not url.startswith("https://cloud.debian.org/images/cloud/"):
        raise ValueError("OFFICIAL_HTTPS_SOURCE_REQUIRED")
    fd, partial = tempfile.mkstemp(prefix="download-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as output, urllib.request.urlopen(url, timeout=60) as response:
            # Debian's primary service redirects binaries to its mirrors.
            # HTTPS transport and the pinned digest remain mandatory.
            if not response.url.startswith("https://"):
                raise ValueError("UNEXPECTED_IMAGE_REDIRECT")
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 4 * 1024**3:
                    raise ValueError("IMAGE_DOWNLOAD_TOO_LARGE")
                output.write(chunk)
        if digest(partial) != expected:
            raise ValueError("DOWNLOADED_IMAGE_HASH_MISMATCH")
        # Hard-link creation refuses to replace an existing artifact.
        os.link(partial, destination)
    finally:
        Path(partial).unlink(missing_ok=True)


def image_info(qemu, path, image_format):
    result = subprocess.run([str(qemu), "info", "--output=json", "-f", image_format, str(path)],
                            capture_output=True, check=True, text=True)
    return json.loads(result.stdout)


def prepare(output, qemu):
    lock = json.loads((ROOT / "infra/vmware/debian-image.lock.json").read_text())
    version = subprocess.run([str(qemu), "--version"], capture_output=True, check=True, text=True)
    if not re.search(r"qemu-img version " + re.escape(lock["qemu_version"]) + r"(?:\s|$)", version.stdout):
        raise ValueError("PINNED_QEMU_REQUIRED")
    output = Path(output).resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("IMAGE_CACHE_OUTSIDE_REPOSITORY_REQUIRED")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = output / lock["filename"]
    verified_download(lock["source"] + lock["filename"], source, lock["sha512"])
    info = image_info(qemu, source, "qcow2")
    if info["virtual-size"] != lock["virtual_size_bytes"] or info.get("backing-filename") or info.get("data-file"):
        raise ValueError("UNEXPECTED_SOURCE_DISK_LAYOUT")
    vmdk = output / "arcia-debian-13-base.vmdk"
    receipt_path = output / "image-receipt.json"
    if vmdk.exists():
        if vmdk.is_symlink() or not receipt_path.exists():
            raise ValueError("EXISTING_UNATTESTED_VMDK")
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("source_sha512") != lock["sha512"] or receipt.get("vmdk_sha512") != digest(vmdk):
            raise ValueError("EXISTING_VMDK_HASH_MISMATCH")
        return receipt
    if receipt_path.exists():
        raise ValueError("EXISTING_RECEIPT_WITHOUT_DISK")
    # Conversion is deliberately separate from import/power-on on vCenter.
    with tempfile.TemporaryDirectory(prefix="convert-", dir=output) as temporary:
        converted = Path(temporary) / "disk.vmdk"
        subprocess.run([str(qemu), "convert", "-f", "qcow2", "-O", "vmdk", "-o",
                        "subformat=streamOptimized,compat6=on", str(source), str(converted)],
                       check=True, capture_output=True)
        details = image_info(qemu, converted, "vmdk")
        if details["virtual-size"] != lock["virtual_size_bytes"] or details.get("backing-filename"):
            raise ValueError("UNEXPECTED_CONVERTED_DISK_LAYOUT")
        receipt = {"status": "disk_prepared", "source_sha512": lock["sha512"],
                   "vmdk_sha512": digest(converted), "qemu_version": lock["qemu_version"],
                   "open_vm_tools_installed": False, "boot_verified": False, "deployed": False}
        os.link(converted, vmdk)
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--qemu", default="qemu-img")
    args = parser.parse_args()
    try:
        result = prepare(args.output, args.qemu)
        print(json.dumps(result))
        return 0
    except Exception:
        print(json.dumps({"status": "blocked", "code": "DEBIAN_IMAGE_PREPARATION_FAILED", "deployed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
