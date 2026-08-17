#!/usr/bin/env python3
"""Assert the two embedded copies of the working-with-the-human block match."""
import pathlib
import sys

BEGIN = "<!-- plan-foundry:working-with-the-human:begin -->"
END = "<!-- plan-foundry:working-with-the-human:end -->"
SITES = ["CLAUDE.md", ".claude/skills/init-plan-foundry/operating-rules.md"]


def extract(path):
    p = pathlib.Path(path)
    if not p.is_file():
        return None, f"{path}: file not found"
    text = p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return None, (
            f"{path}: expected exactly one marker pair, found "
            f"{text.count(BEGIN)} begin and {text.count(END)} end"
        )
    b, e = text.index(BEGIN), text.index(END)
    if e < b:
        return None, f"{path}: end marker precedes begin marker"
    return text[b + len(BEGIN):e].strip(), None


def main():
    bodies, errors = [], []
    for site in SITES:
        body, err = extract(site)
        if err:
            errors.append(err)
        else:
            bodies.append(body)
    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1
    if bodies[0] != bodies[1]:
        import difflib
        print(f"FAIL: embedded copies differ between {SITES[0]} and {SITES[1]}")
        diff = difflib.unified_diff(
            bodies[0].split("\n"), bodies[1].split("\n"),
            SITES[0], SITES[1], lineterm="",
        )
        for line in list(diff)[:20]:
            print(line)
        return 1
    print("OK: both copies identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
