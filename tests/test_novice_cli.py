from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class NoviceCliTests(unittest.TestCase):
    def test_finish_refuses_an_incomplete_matrix_before_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = pathlib.Path(temporary) / "repo"
            shutil.copytree(
                ROOT,
                repo,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "__pycache__",
                    "results",
                    "output",
                    "build-manifest.json",
                ),
            )
            (repo / "results").mkdir()
            result = subprocess.run(
                [str(repo / "il2-diagnostic.sh"), "finish"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not ready", result.stderr)
            self.assertFalse(any(repo.glob("PRIVATE-il2-xid109-results-*")))


if __name__ == "__main__":
    unittest.main()
