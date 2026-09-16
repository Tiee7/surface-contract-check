"""Command-line entry point."""

import argparse
import json
from pathlib import Path

from .core import check_contract


def _parser():
    parser = argparse.ArgumentParser(
        prog="surface-contract",
        description="Catch conflicting values across product pages.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="evaluate a JSON contract")
    check.add_argument("contract")
    check.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _human_lines(report):
    if report["status"] == "error":
        return ["ERROR %s" % message for message in report.get("errors", ["unknown error"])]
    lines = []
    for check in report["checks"]:
        values = check["values"]
        if check["status"] == "pass":
            detail = " = ".join(values)
            lines.append("PASS %s: %s" % (check["name"], detail))
        else:
            detail = " != ".join(values) if values else "; ".join(check["errors"])
            lines.append("FAIL %s: %s" % (check["name"], detail))
    return lines


def main(argv=None):
    args = _parser().parse_args(argv)
    report = check_contract(Path(args.contract))
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("\n".join(_human_lines(report)))
    return {"pass": 0, "fail": 1}.get(report["status"], 2)


def entrypoint():
    raise SystemExit(main())
