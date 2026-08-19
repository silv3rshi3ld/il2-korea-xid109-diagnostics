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
            [
                "baseline",
                "descriptor-qa",
                "descriptor-heap",
                "single-queue",
                "no-descriptor-buffer",
                "sync",
            ],
        )
        self.assertEqual(records[0][1:3], ["breadcrumbs", ""])
        self.assertEqual(records[1][1:3], ["breadcrumbs,descriptor_qa_checks", ""])
        self.assertEqual(records[2][1:3], ["breadcrumbs,descriptor_heap", ""])
        self.assertEqual(records[3][1:3], ["breadcrumbs,single_queue", ""])
        self.assertEqual(records[4][1:3], ["breadcrumbs", "VK_EXT_descriptor_buffer"])
        self.assertEqual(records[5][1:3], ["breadcrumbs_sync", ""])
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
        self.assertEqual(
            patch_record["diff_sha256"],
            "87ff08af931dcfd04acb3000333f716c71117069667da6b3b4c0ddf1d81325be",
        )
        self.assertEqual(source_lock["build"]["source_date_epoch"], "1786468653")
        self.assertEqual(source_lock["build"]["locale"], "C")
        self.assertEqual(source_lock["build"]["timezone"], "UTC")
        self.assertIn("-Denable_descriptor_qa=true", source_lock["build"]["meson_arguments"])

    def test_runtime_matrix_does_not_enable_optional_fault_or_vk_debug(self) -> None:
        matrix = (ROOT / "config/test-matrix.conf").read_text()
        configs = [
            line.split("|")[1]
            for line in matrix.splitlines()
            if line and not line.startswith("#")
        ]
        self.assertNotIn("fault", ",".join(configs).split(","))
        self.assertNotIn("vk_debug", matrix.lower())

    def test_no_xid_policy_requires_ten_minutes(self) -> None:
        policy = json.loads((ROOT / "config/test-policy.json").read_text())
        self.assertEqual(policy["no_xid_observation_seconds"], 600)
        self.assertEqual(
            policy["recommended_case_order"],
            [
                "baseline",
                "descriptor-qa",
                "descriptor-heap",
                "single-queue",
                "no-descriptor-buffer",
                "sync",
            ],
        )

    def test_tester_notice_and_third_party_boundaries_exist(self) -> None:
        terms = (ROOT / "TESTER-TERMS.md").read_text()
        notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text()
        self.assertIn("Notice version: `2026-08-19.1`", terms)
        self.assertIn("Nothing is uploaded automatically", terms)
        self.assertIn("GNU Lesser General Public License", notices)
        self.assertIn("corresponding-source", notices)
        self.assertTrue((ROOT / "LICENSES/VKD3D-Proton-LGPL-2.1.txt").is_file())
        self.assertTrue((ROOT / "LICENSES/VKD3D-Proton-COPYING.txt").is_file())

    def test_default_result_pack_excludes_nvidia_report(self) -> None:
        packer = (ROOT / "tools/pack-results.sh").read_text()
        self.assertIn("--exclude='results/nvidia-reports'", packer)
        self.assertIn("PRIVATE-il2-xid109-results", packer)


if __name__ == "__main__":
    unittest.main()
