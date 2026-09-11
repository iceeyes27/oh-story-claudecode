"""Registration must remain visible to the installed scanner's fenced parser."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILLS = Path(__file__).resolve().parents[2]


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for rel in ["deslop-register/scripts/register.py", "_shared/scripts/check-ai-patterns.js",
                    "_shared/references/banned-words.md"]:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SKILLS / rel, target)
        self.rules = self.root / "_shared/references/banned-words.md"

    def register(self, kind, value, expected=0):
        result = subprocess.run([sys.executable, str(self.root / "deslop-register/scripts/register.py"),
                                 kind, value], capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stderr)

    def scan(self, prose):
        chapter = self.root / "chapter.md"
        chapter.write_text(prose, encoding="utf-8")
        result = subprocess.run(["node", str(self.root / "_shared/scripts/check-ai-patterns.js"),
                                 "--json", "--fail-on=blocking", str(chapter)],
                                capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["findings"]

    def test_phrase_is_parsed_and_duplicate_is_noop(self):
        phrase = "专供回归检查的短语"
        self.register("phrase", phrase)
        before = self.rules.read_bytes()
        self.register("phrase", phrase)
        self.assertEqual(before, self.rules.read_bytes())
        findings = self.scan(phrase + "。")
        self.assertTrue(any(f["type"] == "banned-word-exact" for f in findings))
        self.assertTrue(all(f["severity"] == "advisory" for f in findings))

    def test_regex_including_local_expository_command_is_parsed(self):
        for kind, suffix in [("syna", "syna"), ("antithesis", "antithesis"),
                             ("expository", "expository-contrast"),
                             ("dangling-identity", "dangling-identity"), ("body-shell", "body-shell")]:
            with self.subTest(kind=kind):
                phrase = "校验" + kind + "提示"
                rule = "/" + phrase + "/"
                self.register(kind, rule)
                before = self.rules.read_bytes()
                self.register(kind, rule)
                self.assertEqual(before, self.rules.read_bytes())
                self.assertTrue(any(f["type"] == "banned-word-" + suffix
                                    for f in self.scan(phrase + "。")))

    def test_invalid_regex_does_not_modify_rules(self):
        before = self.rules.read_bytes()
        self.register("expository", "/[/", expected=1)
        self.assertEqual(before, self.rules.read_bytes())


if __name__ == "__main__":
    unittest.main()
