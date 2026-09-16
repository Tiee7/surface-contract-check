"""Contract evaluation engine."""

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)

    def text(self):
        return " ".join(" ".join(self.parts).split())


def _visible_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def _error_report(path: Path, message: str) -> dict:
    return {
        "status": "error",
        "contract": str(path),
        "sources": {},
        "checks": [],
        "errors": [message],
    }


def _load_source(source: dict, contract_path: Path):
    if "path" in source:
        locator = (contract_path.parent / source["path"]).resolve()
        raw = locator.read_bytes()
        evidence = {"locator": str(locator)}
    elif "url" in source:
        locator = source["url"]
        if urlsplit(locator).scheme not in ("http", "https"):
            raise ValueError("only http:// and https:// URLs are allowed: %s" % locator)
        request = Request(locator, headers={"User-Agent": "surface-contract-check/0.1"})
        with urlopen(request, timeout=source.get("timeout", 15)) as response:
            raw = response.read()
            evidence = {
                "locator": response.geturl(),
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
            }
    else:
        raise ValueError("source requires either 'path' or 'url'")

    evidence.update({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    decoded = raw.decode(source.get("encoding", "utf-8"))
    if source.get("format") == "html":
        decoded = _visible_text(decoded)
    return decoded, evidence


def check_contract(config_path: Path) -> dict:
    """Evaluate one surface contract."""
    path = Path(config_path).resolve()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _error_report(path, "could not load contract: %s" % exc)
    source_text = {}
    source_evidence = {}

    try:
        for source_id, source in config["sources"].items():
            source_text[source_id], source_evidence[source_id] = _load_source(source, path)
    except (KeyError, OSError, UnicodeError, ValueError) as exc:
        return _error_report(path, str(exc))

    compiled = {}
    try:
        for check_index, check in enumerate(config["checks"]):
            if check.get("rule") != "equal":
                raise ValueError("unsupported rule: %s" % check.get("rule"))
            if len(check["extract"]) < 2:
                raise ValueError("equal rule requires at least two extractions")
            for extraction_index, extraction in enumerate(check["extract"]):
                source_id = extraction["source"]
                if source_id not in source_text:
                    raise ValueError("unknown source: %s" % source_id)
                pattern = re.compile(extraction["pattern"])
                if pattern.groups != 1:
                    raise ValueError(
                        "pattern for source '%s' must contain exactly one capture group" % source_id
                    )
                compiled[(check_index, extraction_index)] = pattern
    except re.error as exc:
        return _error_report(path, "invalid regular expression: %s" % exc)
    except ValueError as exc:
        return _error_report(path, str(exc))
    except KeyError as exc:
        return _error_report(path, "invalid contract field: %s" % exc)

    checks = []
    for check_index, check in enumerate(config["checks"]):
        values = []
        errors = []
        for extraction_index, extraction in enumerate(check["extract"]):
            source_id = extraction["source"]
            match = compiled[(check_index, extraction_index)].search(source_text[source_id])
            if match is None:
                errors.append("source '%s': pattern did not match" % source_id)
                continue
            values.append(match.group(1))
        passed = not errors and len(set(values)) <= 1
        checks.append(
            {
                "name": check["name"],
                "status": "pass" if passed else "fail",
                "values": values,
                "errors": errors,
            }
        )

    return {
        "status": "pass" if all(item["status"] == "pass" for item in checks) else "fail",
        "contract": str(path),
        "sources": source_evidence,
        "checks": checks,
    }
