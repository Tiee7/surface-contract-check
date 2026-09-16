import hashlib
import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path

import surface_contract.core as core


class CoreContractTests(unittest.TestCase):
    def write_contract(self, root, sources, checks):
        path = root / "contract.json"
        path.write_text(json.dumps({"sources": sources, "checks": checks}), encoding="utf-8")
        return path

    def test_check_contract_api_exists(self):
        self.assertTrue(hasattr(core, "check_contract"))

    def test_different_values_fail_with_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sales = b"<h1>Plans</h1><p>Starter: $99</p>"
            docs = b"<h1>Docs</h1><p>Starter: $79</p>"
            (root / "sales.html").write_bytes(sales)
            (root / "docs.html").write_bytes(docs)
            config = {
                "sources": {
                    "sales": {"path": "sales.html", "format": "html"},
                    "docs": {"path": "docs.html", "format": "html"},
                },
                "checks": [
                    {
                        "name": "starter price",
                        "rule": "equal",
                        "extract": [
                            {"source": "sales", "pattern": r"Starter:\s*\$(\d+)"},
                            {"source": "docs", "pattern": r"Starter:\s*\$(\d+)"},
                        ],
                    }
                ],
            }
            config_path = root / "contract.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            report = core.check_contract(config_path)

            self.assertEqual("fail", report["status"])
            self.assertEqual(str(config_path.resolve()), report["contract"])
            self.assertEqual(["99", "79"], report["checks"][0]["values"])
            self.assertEqual("fail", report["checks"][0]["status"])
            self.assertEqual(hashlib.sha256(sales).hexdigest(), report["sources"]["sales"]["sha256"])
            self.assertEqual(len(docs), report["sources"]["docs"]["bytes"])

    def test_equal_values_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sales.txt").write_text("Starter: $99", encoding="utf-8")
            (root / "docs.txt").write_text("Starter: $99", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {"sales": {"path": "sales.txt"}, "docs": {"path": "docs.txt"}},
                [{
                    "name": "starter price",
                    "rule": "equal",
                    "extract": [
                        {"source": "sales", "pattern": r"\$(\d+)"},
                        {"source": "docs", "pattern": r"\$(\d+)"},
                    ],
                }],
            )

            report = core.check_contract(config_path)

            self.assertEqual("pass", report["status"])
            self.assertEqual(["99", "99"], report["checks"][0]["values"])

    def test_missing_pattern_fails_with_named_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs.txt").write_text("No price here", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {"docs": {"path": "docs.txt"}},
                [{
                    "name": "starter price",
                    "rule": "equal",
                    "extract": [
                        {"source": "docs", "pattern": r"No (price)"},
                        {"source": "docs", "pattern": r"\$(\d+)"},
                    ],
                }],
            )

            report = core.check_contract(config_path)

            self.assertEqual("fail", report["status"])
            self.assertEqual(["source 'docs': pattern did not match"], report["checks"][0]["errors"])

    def test_invalid_regex_returns_error_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs.txt").write_text("Starter: $99", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {"docs": {"path": "docs.txt"}},
                [{
                    "name": "starter price",
                    "rule": "equal",
                    "extract": [
                        {"source": "docs", "pattern": "("},
                        {"source": "docs", "pattern": r"\$(\d+)"},
                    ],
                }],
            )

            try:
                report = core.check_contract(config_path)
            except Exception as exc:
                self.fail("invalid regex escaped instead of returning evidence: %s" % exc)

            self.assertEqual("error", report["status"])
            self.assertIn("invalid regular expression", report["errors"][0])

    def test_non_http_url_returns_error_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = self.write_contract(
                root,
                {"docs": {"url": "file:///etc/hosts"}},
                [],
            )

            try:
                report = core.check_contract(config_path)
            except Exception as exc:
                self.fail("unsupported URL escaped instead of returning evidence: %s" % exc)

            self.assertEqual("error", report["status"])
            self.assertIn("only http:// and https:// URLs are allowed", report["errors"][0])

    def test_http_sources_are_fetched_and_compared(self):
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sales.txt").write_text("Starter: $99", encoding="utf-8")
            (root / "docs.txt").write_text("Starter: $99", encoding="utf-8")
            handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(root), **kwargs)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:%d" % server.server_port
                config_path = self.write_contract(
                    root,
                    {"sales": {"url": base + "/sales.txt"}, "docs": {"url": base + "/docs.txt"}},
                    [{
                        "name": "starter price",
                        "rule": "equal",
                        "extract": [
                            {"source": "sales", "pattern": r"\$(\d+)"},
                            {"source": "docs", "pattern": r"\$(\d+)"},
                        ],
                    }],
                )

                try:
                    report = core.check_contract(config_path)
                except Exception as exc:
                    self.fail("HTTP source escaped instead of returning evidence: %s" % exc)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual("pass", report["status"])
            self.assertEqual(200, report["sources"]["sales"]["status"])

    def test_unsupported_rule_returns_error_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs.txt").write_text("Starter: $99", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {"docs": {"path": "docs.txt"}},
                [{
                    "name": "starter price",
                    "rule": "approximately_equal",
                    "extract": [{"source": "docs", "pattern": r"\$(\d+)"}],
                }],
            )

            report = core.check_contract(config_path)

            self.assertEqual("error", report["status"])
            self.assertIn("unsupported rule", report["errors"][0])

    def test_pattern_requires_exactly_one_capture_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs.txt").write_text("Starter: $99", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {"docs": {"path": "docs.txt"}},
                [{
                    "name": "starter price",
                    "rule": "equal",
                    "extract": [
                        {"source": "docs", "pattern": r"\$\d+"},
                        {"source": "docs", "pattern": r"\$(\d+)"},
                    ],
                }],
            )

            try:
                report = core.check_contract(config_path)
            except Exception as exc:
                self.fail("capture-group error escaped instead of returning evidence: %s" % exc)

            self.assertEqual("error", report["status"])
            self.assertIn("exactly one capture group", report["errors"][0])

    def test_unknown_source_returns_error_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs.txt").write_text("Starter: $99", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {"docs": {"path": "docs.txt"}},
                [{
                    "name": "starter price",
                    "rule": "equal",
                    "extract": [
                        {"source": "docs", "pattern": r"\$(\d+)"},
                        {"source": "missing", "pattern": r"\$(\d+)"},
                    ],
                }],
            )

            try:
                report = core.check_contract(config_path)
            except Exception as exc:
                self.fail("unknown source escaped instead of returning evidence: %s" % exc)

            self.assertEqual("error", report["status"])
            self.assertIn("unknown source", report["errors"][0])

    def test_html_ignores_script_and_style_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sales.html").write_text(
                "<script>const label='Starter: $79'</script>"
                "<style>.price:after{content:'Starter: $79'}</style>"
                "<p>Starter: $99</p>",
                encoding="utf-8",
            )
            (root / "docs.html").write_text("<p>Starter: $99</p>", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {
                    "sales": {"path": "sales.html", "format": "html"},
                    "docs": {"path": "docs.html", "format": "html"},
                },
                [{
                    "name": "starter price",
                    "rule": "equal",
                    "extract": [
                        {"source": "sales", "pattern": r"Starter:\s*\$(\d+)"},
                        {"source": "docs", "pattern": r"Starter:\s*\$(\d+)"},
                    ],
                }],
            )

            report = core.check_contract(config_path)

            self.assertEqual("pass", report["status"])
            self.assertEqual(["99", "99"], report["checks"][0]["values"])

    def test_equal_rule_requires_two_extractions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs.txt").write_text("Starter: $99", encoding="utf-8")
            config_path = self.write_contract(
                root,
                {"docs": {"path": "docs.txt"}},
                [{
                    "name": "starter price",
                    "rule": "equal",
                    "extract": [{"source": "docs", "pattern": r"\$(\d+)"}],
                }],
            )

            report = core.check_contract(config_path)

            self.assertEqual("error", report["status"])
            self.assertIn("at least two extractions", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
