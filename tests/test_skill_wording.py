"""The skills must read correctly in every host: ChatGPT, Codex and the Researchzy research agent."""
from __future__ import annotations

import unittest
from pathlib import Path

SKILLS = Path(__file__).parents[1] / "plugins" / "researchzy" / "skills"
HOST_SPECIFIC = ("Use the host connection flow", "explain that Researchzy must be connected",
                 "Confirm that the tools are connected")


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class SkillWordingTests(unittest.TestCase):
    def test_skills_do_not_assume_a_host_connection_flow(self):
        for path in sorted(SKILLS.rglob("*.md")):
            text = normalized(path)
            for phrase in HOST_SPECIFIC:
                self.assertNotIn(phrase, text, f"{path.relative_to(SKILLS)}: {phrase!r}")

    def test_authorization_failures_still_forbid_asking_for_credentials(self):
        for name in ("researchzy/SKILL.md", "researchzy/references/researchzy-source.md"):
            text = normalized(SKILLS / name)
            self.assertIn("never request", text)
            self.assertIn("connection flow when", text)


if __name__ == "__main__":
    unittest.main()
