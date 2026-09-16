import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import surface_contract.cli as cli


class CliTests(unittest.TestCase):
    def test_main_api_exists(self):
        self.assertTrue(hasattr(cli, "main"))

    def write_contract(self, root, left_value, right_value):
        (root / "left.txt").write_text("Starter: $%s" % left_value, encoding="utf-8")
        (root / "right.txt").write_text("Starter: $%s" % right_value, encoding="utf-8")
        contract = {
            "sources": {
                "left": {"path": "left.txt"},
                "right": {"path": "right.txt"},
            },
            "checks": [{
                "name": "starter price",
                "rule": "equal",
                "extract": [
                    {"source": "left", "pattern": r"\$(\d+)"},
                    {"source": "right", "pattern": r"\$(\d+)"},
                ],
            }],
        }
        path = root / "contract.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        return path

    def test_json_failure_returns_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract = self.write_contract(Path(temp_dir), "99", "79")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = cli.main(["check", str(contract), "--json"])

            self.assertEqual(1, exit_code)
            self.assertEqual("fail", json.loads(output.getvalue())["status"])

    def test_human_pass_output_returns_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract = self.write_contract(Path(temp_dir), "99", "99")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = cli.main(["check", str(contract)])

            self.assertEqual(0, exit_code)
            self.assertIn("PASS starter price: 99 = 99", output.getvalue())

    def test_invalid_contract_returns_two(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = cli.main(["check", "/definitely/missing/contract.json", "--json"])

        self.assertEqual(2, exit_code)
        self.assertEqual("error", json.loads(output.getvalue())["status"])


if __name__ == "__main__":
    unittest.main()
