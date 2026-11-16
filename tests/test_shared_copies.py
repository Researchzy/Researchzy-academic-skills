"""A script that several skills carry must be the same file in each: every skill installs on its own,
so each keeps its own copy, and a fix made in one copy must reach the others."""
from __future__ import annotations

import unittest
from collections import defaultdict
from pathlib import Path

PLUGINS = Path(__file__).parents[1] / "plugins"


class SharedCopyTests(unittest.TestCase):
    def test_scripts_with_the_same_name_are_identical(self):
        copies = defaultdict(list)
        for path in sorted(PLUGINS.glob("*/skills/*/**/scripts/*.py")):
            copies[path.name].append(path)
        for name, paths in copies.items():
            first = paths[0].read_bytes()
            for other in paths[1:]:
                self.assertEqual(other.read_bytes(), first,
                                 f"{other.relative_to(PLUGINS)} differs from {paths[0].relative_to(PLUGINS)}")


if __name__ == "__main__":
    unittest.main()
