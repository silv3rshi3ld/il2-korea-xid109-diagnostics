from __future__ import annotations

import hashlib
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
    def test_controlled_matrix_is_exact_and_ordered(self) -> None:
        records = []
        for line in (ROOT / "config/test-matrix.conf").read_text().splitlines():
            if line and not line.startswith("#"):
                records.append(line.split("|"))
        self.assertEqual(
            [record[0] for record in records],
            ["baseline", "single-queue", "no-descriptor-buffer", "sync"],
        )
        self.assertEqual(records[0][1:3], ["breadcrumbs", ""])
        self.assertEqual(records[1][1:3], ["breadcrumbs,single_queue", ""])
        self.assertEqual(records[2][1:3], ["breadcrumbs", "VK_EXT_descriptor_buffer"])
        self.assertEqual(records[3][1:3], ["breadcrumbs_sync", ""])
        self.assertNotIn("Great Battles", (ROOT / "config/test-matrix.conf").read_text())

    def test_source_lock_and_patch_hash(self) -> None:
        source_lock = json.loads((ROOT / "build/source-lock.json").read_text())
        self.assertEqual(
            source_lock["failing_proton"]["commit"],
            "0dda688b3840c381dfb76f87b81c9e50c846d627",
        )
        self.assertEqual(
            source_lock["vkd3d_proton"]["commit"],
            "238f157e1d64f90e0d90593557c092ab8af6e0a3",
        )
        patch_record = source_lock["patches"][0]
        patch = ROOT / patch_record["path"]
        self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(), patch_record["sha256"])

    def test_runtime_matrix_does_not_enable_optional_fault_or_vk_debug(self) -> None:
        matrix = (ROOT / "config/test-matrix.conf").read_text()
        self.assertNotIn("fault", matrix.lower())
        self.assertNotIn("vk_debug", matrix.lower())


if __name__ == "__main__":
    unittest.main()
