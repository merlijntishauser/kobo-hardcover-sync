"""docs/sync-rules.md promises things. This holds it to them: every rule
there names at least one test, and every test it names exists."""

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "sync-rules.md"
RULE = re.compile(r"^- \*\*([A-Z]\d+)\*\*", re.M)
TEST = re.compile(r"`(tests/test_\w+\.py)::(test_\w+)`")


def rules():
    text = DOC.read_text().split("## Known limits")[0]
    starts = [(m.group(1), m.start()) for m in RULE.finditer(text)]
    ends = [s for _, s in starts[1:]] + [len(text)]
    return {name: text[start:end].split("\n## ")[0] for (name, start), end in zip(starts, ends, strict=True)}


def functions_in(path):
    return {n.name for n in ast.walk(ast.parse((ROOT / path).read_text())) if isinstance(n, ast.FunctionDef)}


def test_every_rule_names_a_test_that_exists():
    found = rules()
    assert len(found) > 40 and len(found) == len(RULE.findall(DOC.read_text())), "a rule name is used twice"
    for name, text in found.items():
        cited = TEST.findall(text)
        assert cited, f"rule {name} names no test"
        assert "Tests:" in text, f"rule {name} has no Tests: line"
        for path, test in cited:
            assert (ROOT / path).is_file(), f"rule {name}: {path} does not exist"
            assert test in functions_in(path), f"rule {name}: {path} has no {test}"


def test_the_limits_point_at_rules_that_exist():
    limits = DOC.read_text().split("## Known limits")[1]
    for name in re.findall(r"\(([A-Z]\d+)\)", limits):
        assert name in rules(), f"the limits mention {name}, which is not a rule"
