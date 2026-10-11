import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('debian_image', ROOT / 'scripts/prepare_debian_image.py')
image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image)


class ImageIntegrityTests(unittest.TestCase):
    def test_corrupted_cache_is_refused_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'image.qcow2'
            destination.write_bytes(b'CORRUPTED_SYNTHETIC_DISK')
            with patch.object(image.urllib.request, 'urlopen') as network:
                with self.assertRaisesRegex(ValueError, 'EXISTING_IMAGE_HASH_MISMATCH'):
                    image.verified_download('https://cloud.debian.org/images/cloud/example', destination, 'a' * 128)
                network.assert_not_called()

    def test_valid_cache_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'image.qcow2'
            destination.write_bytes(b'SYNTHETIC_DISK')
            with patch.object(image.urllib.request, 'urlopen') as network:
                image.verified_download('https://cloud.debian.org/images/cloud/example', destination,
                                        hashlib.sha512(b'SYNTHETIC_DISK').hexdigest())
                network.assert_not_called()

    def test_arbitrary_download_source_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'OFFICIAL_HTTPS_SOURCE_REQUIRED'):
                image.verified_download('http://example.invalid/image', Path(directory) / 'image', 'a' * 128)


if __name__ == '__main__':
    unittest.main()
