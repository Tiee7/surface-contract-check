# Surface Contract Check

Catch conflicting prices, limits, and versions before customers do.

Product facts often appear on a pricing page, documentation, comparison pages, structured data, and onboarding copy. A small edit can leave those surfaces disagreeing. Surface Contract Check turns selected public values into a repeatable release check with source hashes and a CI-friendly exit code.

## Try it

Python 3.9 or newer is the only runtime requirement.

```bash
unzip surface-contract-check-0.1.0.zip
cd surface-contract-check-0.1.0
python3 -m venv .venv
.venv/bin/pip install .
```

The included passing contract returns `0`:

```bash
surface-contract check examples/passing-contract.json
# PASS starter monthly price: 99 = 99
```

The deliberately inconsistent contract returns `1`:

```bash
surface-contract check examples/failing-contract.json
# FAIL starter monthly price: 99 != 79
```

Use `--json` to retain source locators, byte counts, SHA-256 hashes, extracted values, and check results:

```bash
surface-contract check examples/failing-contract.json --json
```

## Define a contract

```json
{
  "sources": {
    "pricing": {
      "url": "https://example.com/pricing",
      "format": "html"
    },
    "docs": {
      "url": "https://example.com/docs/billing",
      "format": "html"
    }
  },
  "checks": [
    {
      "name": "starter monthly price",
      "rule": "equal",
      "extract": [
        {"source": "pricing", "pattern": "Starter:\\s*\\$(\\d+)"},
        {"source": "docs", "pattern": "Starter:\\s*\\$(\\d+)"}
      ]
    }
  ]
}
```

Each source uses either an HTTP(S) `url` or a `path` relative to the contract file. Set `"format": "html"` to compare visible text rather than raw markup. Every extraction pattern must contain exactly one capture group. Version `0.1.0` supports the `equal` rule.

Exit codes:

- `0`: every contract passed;
- `1`: at least one value was missing or inconsistent;
- `2`: the contract, source, or regular expression was invalid or unavailable.

## CI

Vendor or extract the release into your repository, install it, and run a contract after generated pages are available:

```yaml
- run: pip install ./tools/surface-contract-check
- run: surface-contract check contracts/product-facts.json --json
```

The included workflow tests Python 3.9, 3.11, and 3.13.

## Evidence and limits

The report proves what the configured public sources returned during that run. It does not execute client-side JavaScript, inspect private dashboards, determine checkout billing, establish legal compliance, or prove which conflicting value is authoritative. Choose the canonical value with the product owner, then repair and test the agreed surfaces.

This project was implemented with AI assistance and human verification by Tiee. It does not contain client code or claim a customer relationship.

Need the canonical fact table, focused page repairs, assertions, and before/after handoff? See the [fixed-scope product-content repair service](https://tiee-dev-onboarding-repair.chrchill.chatgpt.site).

## License

MIT
