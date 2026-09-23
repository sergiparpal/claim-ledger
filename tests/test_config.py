"""ledger.config: loading and validating claim-ledger.toml.

Every invalid config must raise ConfigError naming the offending key, and must
never come back as a Config built from defaults. The base for every case is
the committed claim-ledger.toml, so these tests also hold the sample valid.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from ledger import config
from ledger.config import HUMAN, LOW, REVIEW, ConfigError

SAMPLE_PATH = Path(__file__).resolve().parent.parent / config.CONFIG_FILENAME
SAMPLE = SAMPLE_PATH.read_text(encoding="utf-8")


def edited(old, new, text=SAMPLE):
    """The sample with one exact fragment replaced. Fails if the fragment drifted."""
    if text.count(old) != 1:
        raise AssertionError(f"fragment not in the sample exactly once: {old!r}")
    return text.replace(old, new)


def without_table(name, text=SAMPLE):
    """The sample with the table [name], its body and its subtables removed."""
    pattern = rf"^\[{re.escape(name)}(?:\.[^\]]+)?\]\n(?:(?!\[).*\n?)*"
    result, count = re.subn(pattern, "", text, flags=re.MULTILINE)
    if not count:
        raise AssertionError(f"table not in the sample: [{name}]")
    return result


def small_config(checks=None, human=(), low=()):
    """A minimal valid config. Every check id gets the scope ["**/*"]."""
    checks = checks or {}
    q = json.dumps
    lines = ["[checks]"]
    lines += [f"{check_id} = {q(list(invocations))}" for check_id, invocations in checks.items()]
    lines += ["[checks.scope]"]
    lines += [f'{check_id} = ["**/*"]' for check_id in checks]
    lines += ["[checks.aliases]"]
    lines += ["[tiers]", f"HUMAN = {q(list(human))}", f"LOW = {q(list(low))}",
              'default = "REVIEW"',
              "[extractor]", 'base_url = "https://example.invalid/api/v1"',
              'auth = "x-api-key"', 'key_env = "TEST_KEY"', 'model = "m"',
              'provider = "p/fp8"', 'answer_shape = "json_schema"',
              "timeout_s = 1", "max_report_chars = 1", "[extractor.parameters]",
              "[budget]", "turn_timeout_s = 1",
              "[log]", "max_command_chars = 10",
              "[gate]", "enabled = false",
              "[corpus]", "capture = false"]
    return "\n".join(lines) + "\n"


class ConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def load_text(self, text):
        path = self.dir / config.CONFIG_FILENAME
        path.write_text(text, encoding="utf-8")
        return config.load(path)

    def assertRejects(self, text, key):
        """Loading fails, naming key, and returns nothing."""
        with self.assertRaises(ConfigError) as caught:
            self.load_text(text)
        self.assertEqual(caught.exception.key, key, str(caught.exception))
        self.assertIn(key, str(caught.exception))
        return caught.exception


class ValidConfigTest(ConfigTest):
    def test_sample_loads_with_every_value_as_written(self):
        cfg = config.load(SAMPLE_PATH)
        self.assertEqual(cfg.checks, (
            config.Check("python-suite", ("pytest", "pytest -q", "python -m pytest",
                                          "uv run pytest")),
            config.Check("js-suite", ("npm test",)),
            config.Check("types", ("mypy src",)),
            config.Check("lint", ("ruff check .",)),
        ))
        self.assertEqual({k: [g.text for g in v] for k, v in cfg.scopes.items()},
                         {"python-suite": ["src/**/*.py", "tests/**/*.py"],
                          "js-suite": ["src/**/*.ts"],
                          "types": ["src/**/*.py"],
                          "lint": ["**/*"]})
        self.assertEqual([r.text for r in cfg.human],
                         ["migrations/**", "deploy/**", "Bash(git push*)", "Bash(*rm -rf*)"])
        self.assertEqual([r.text for r in cfg.low], ["docs/**", "**/*.md"])
        self.assertEqual(cfg.default_tier, REVIEW)
        self.assertEqual(cfg.extractor, config.Extractor(
            base_url="https://openrouter.ai/api/v1", auth="x-api-key",
            key_env="OPENROUTER_API_KEY", model="deepseek/deepseek-v4.1-flash",
            provider="morph", answer_shape="json_schema",
            parameters={"temperature": 0,
                        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
            timeout_s=12.0, max_report_chars=20000))
        self.assertEqual(cfg.budget, config.Budget(15.0))
        self.assertEqual(cfg.log, config.Log(2000))
        self.assertEqual(cfg.gate, config.Gate(False))
        self.assertEqual(cfg.corpus, config.Corpus(True))

    def test_valid_but_unusual_globs_are_accepted(self):
        for glob in ["**", "a]b", "docs/[!_]*.md", "[]]x", "?.txt", "src/**/**/x"]:
            with self.subTest(glob=glob):
                self.load_text(small_config(low=[glob]))


class UnknownKeyTest(ConfigTest):
    def test_unknown_keys_are_named(self):
        cases = [
            (edited("timeout_s        = 12\n", "timeout_s        = 12\nmodle = \"x\"\n"),
             "extractor.modle"),
            (SAMPLE + "\n[extras]\nenabled = false\n", "extras"),
            (edited('default = "REVIEW"\n', 'default = "REVIEW"\nREVIEW = ["src/**"]\n'),
             "tiers.REVIEW"),
            (edited("turn_timeout_s = 15\n", "turn_timeout_s = 15\nextra = 1\n"),
             "budget.extra"),
            (edited("max_command_chars = 2000\n", "max_command_chars = 2000\nmax_chars = 1\n"),
             "log.max_chars"),
            (edited("capture = true\n", "capture = true\nredact = true\n"), "corpus.redact"),
            (edited('lint         = ["**/*"]\n',
                    'lint         = ["**/*"]\ndocs-suite = ["docs/**"]\n'),
             "checks.scope.docs-suite"),
        ]
        for text, key in cases:
            with self.subTest(key=key):
                self.assertRejects(text, key)


class MissingFileTest(ConfigTest):
    def test_missing_file_is_named(self):
        path = self.dir / config.CONFIG_FILENAME
        with self.assertRaises(ConfigError) as caught:
            config.load(path)
        self.assertIsNone(caught.exception.key)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn("file not found", str(caught.exception))

    def test_unreadable_path_is_named(self):
        with self.assertRaises(ConfigError) as caught:
            config.load(self.dir)  # a directory
        self.assertIn(str(self.dir), str(caught.exception))

    def test_toml_syntax_error_names_the_line(self):
        with self.assertRaises(ConfigError) as caught:
            self.load_text(edited("[tiers]\n", "[tiers\n"))
        self.assertIn("not valid TOML", str(caught.exception))
        self.assertIn("line", str(caught.exception))


class MalformedGlobTest(ConfigTest):
    def test_malformed_globs_are_named(self):
        cases = [
            ('"docs/**"', '"docs/[**"', "tiers.LOW[0]"),             # unclosed [
            ('"docs/**"', '"docs/**.md"', "tiers.LOW[0]"),           # ** inside a segment
            ('"docs/**"', '"[z-a].md"', "tiers.LOW[0]"),             # reversed range
            ('"migrations/**"', '"/migrations/**"', "tiers.HUMAN[0]"),
            ('"migrations/**"', '"~/migrations/**"', "tiers.HUMAN[0]"),
            ('"migrations/**"', '"migrations/"', "tiers.HUMAN[0]"),
            ('"migrations/**"', '"../migrations/**"', "tiers.HUMAN[0]"),
            ('"migrations/**"', '"migrations//x"', "tiers.HUMAN[0]"),
            ('"migrations/**"', r'"migrations\\**"', "tiers.HUMAN[0]"),
            ('"migrations/**"', '""', "tiers.HUMAN[0]"),
            ('"migrations/**"', '" migrations/**"', "tiers.HUMAN[0]"),
            ('"src/**/*.ts"', '"src/**/*.{ts,tsx}"', "checks.scope.js-suite[0]"),
            ('"tests/**/*.py"', '"tests/[a-"', "checks.scope.python-suite[1]"),
        ]
        for old, new, key in cases:
            with self.subTest(glob=new):
                error = self.assertRejects(edited(old, new), key)
                self.assertIn("malformed glob", str(error))


class MissingDefaultTierTest(ConfigTest):
    def test_missing_default_tier_is_named(self):
        error = self.assertRejects(edited('default = "REVIEW"\n', ""), "tiers.default")
        self.assertIn("missing required key", str(error))

    def test_default_tier_must_be_review(self):
        for value in ['"LOW"', '"HUMAN"', '"review"', "1"]:
            with self.subTest(value=value):
                self.assertRejects(edited('default = "REVIEW"', f"default = {value}"),
                                   "tiers.default")


class NoFallbackTest(ConfigTest):
    """Each key and table of the sample is required: removing it never loads."""

    def test_every_key_is_required(self):
        removals = []
        section = None
        for line in SAMPLE.splitlines(keepends=True):
            header = re.fullmatch(r"\[([^\]]+)\]\s*", line)
            if header:
                section = header.group(1)
            elif (section != "checks" and not section.startswith("extractor.parameters")
                    and (key := re.match(r"([A-Za-z0-9_-]+)\s*=", line))):
                # [extractor.parameters] holds whatever a route takes, including
                # nothing at all, so its contents are not required keys.
                removals.append((line, f"{section}.{key.group(1)}"))
        self.assertEqual(len(removals), 19, removals)  # guards against a vacuous pass
        # the alias table's keys are quoted words, not bare keys, so they are
        # covered by test_aliases_name_a_check_that_exists instead
        for line, key in removals:
            with self.subTest(key=key):
                self.assertRejects(edited(line, ""), key)

    def test_every_table_is_required(self):
        for name in ["checks.scope", "checks.aliases", "tiers", "extractor", "budget",
                     "log", "gate", "corpus"]:
            with self.subTest(table=name):
                error = self.assertRejects(without_table(name), name)
                self.assertIn("missing required table", str(error))

    def test_invalid_values_are_named(self):
        cases = [
            ("timeout_s        = 12", 'timeout_s = "12"', "extractor.timeout_s"),
            ("timeout_s        = 12", "timeout_s = 0", "extractor.timeout_s"),
            ("timeout_s        = 12", "timeout_s = true", "extractor.timeout_s"),
            ("timeout_s        = 12", "timeout_s = inf", "extractor.timeout_s"),
            # a budget it cannot fit inside is not a budget
            ("timeout_s        = 12", "timeout_s = 16", "extractor.timeout_s"),
            ("temperature = 0", 'model = "sneaky"', "extractor.parameters.model"),
            ("temperature = 0", "messages = []", "extractor.parameters.messages"),
            ("temperature = 0", "temperature = [0]", "extractor.parameters.temperature"),
            ("max_report_chars = 20000", "max_report_chars = 2.5e4",
             "extractor.max_report_chars"),
            ('model            = "deepseek/deepseek-v4.1-flash"', 'model = ""',
             "extractor.model"),
            ('base_url         = "https://openrouter.ai/api/v1"',
             'base_url = "http://openrouter.ai/api/v1"', "extractor.base_url"),
            ('base_url         = "https://openrouter.ai/api/v1"', 'base_url = ""',
             "extractor.base_url"),
            ('auth             = "x-api-key"', 'auth = "X-Api-Key"', "extractor.auth"),
            ('auth             = "x-api-key"', 'auth = "basic"', "extractor.auth"),
            ('key_env          = "OPENROUTER_API_KEY"', 'key_env = "openrouter_api_key"',
             "extractor.key_env"),
            ('key_env          = "OPENROUTER_API_KEY"', 'key_env = "sk-or-v1-EXAMPLE-NOT-A-KEY"',
             "extractor.key_env"),
            ('provider         = "morph"', 'provider = ""', "extractor.provider"),
            ('provider         = "morph"', 'provider = " morph"', "extractor.provider"),
            ('answer_shape     = "json_schema"', 'answer_shape = "yaml"',
             "extractor.answer_shape"),
            ("turn_timeout_s = 15", "turn_timeout_s = -1", "budget.turn_timeout_s"),
            ("max_command_chars = 2000", "max_command_chars = 0", "log.max_command_chars"),
            ("max_command_chars = 2000", 'max_command_chars = "2000"', "log.max_command_chars"),
            ("max_command_chars = 2000", "max_command_chars = true", "log.max_command_chars"),
            ("enabled = false", "enabled = true", "gate.enabled"),  # v1 never blocks (R-30)
            ("enabled = false", 'enabled = "no"', "gate.enabled"),
            ("capture = true", 'capture = "yes"', "corpus.capture"),
            ('LOW     = ["docs/**", "**/*.md"]', 'LOW = "docs/**"', "tiers.LOW"),
            ('"Bash(git push*)"', '"Edit(deploy/**)"', "tiers.HUMAN[2]"),
            ('"Bash(git push*)"', '"Bash"', "tiers.HUMAN[2]"),
            ('"Bash(git push*)"', '"Bash()"', "tiers.HUMAN[2]"),
            ('"Bash(git push*)"', "42", "tiers.HUMAN[2]"),
        ]
        for old, new, key in cases:
            with self.subTest(value=new):
                self.assertRejects(edited(old, new), key)


class CheckListTest(ConfigTest):
    """[checks] maps a check id to the exact invocations that count as a run."""

    def test_invalid_check_lists_are_named(self):
        cases = [
            ('js-suite     = ["npm test"]', 'js-suite     = "npm test"', "checks.js-suite"),
            ('js-suite     = ["npm test"]', "js-suite     = []", "checks.js-suite"),
            ('js-suite     = ["npm test"]', "js-suite     = [42]", "checks.js-suite[0]"),
            ('js-suite     = ["npm test"]', 'js-suite     = [""]', "checks.js-suite[0]"),
            ('js-suite     = ["npm test"]', 'js-suite     = [" npm test"]', "checks.js-suite[0]"),
            ('"pytest -q"', '"pytest -q || true"', "checks.python-suite[1]"),
            ('"pytest -q"', '"cd src && pytest"', "checks.python-suite[1]"),
            ('"pytest -q"', '"pytest | tee log"', "checks.python-suite[1]"),
            ('"pytest -q"', r'"pytest\nrm -rf x"', "checks.python-suite[1]"),
            ('js-suite     = ["npm test"]', 'js-suite     = ["npm test", "pytest"]',
             "checks.js-suite[1]"),                                 # already under python-suite
            ('lint         = ["ruff check ."]\n',
             'lint         = ["ruff check ."]\n"my suite" = ["make check"]\n',
             'checks."my suite"'),
            ('lint         = ["**/*"]', "lint = []", "checks.scope.lint"),
            # an invocation written into the file-glob table: silent inertness
            ('lint         = ["**/*"]', 'lint = ["python3 -m unittest discover"]',
             "checks.scope.lint[0]"),
            ('"src/**/*.ts"', '"src/** /*.ts"', "checks.scope.js-suite[0]"),
            ('lint         = ["ruff check ."]\n',
             'lint         = ["ruff check ."]\neslint = ["npx eslint ."]\n',
             "checks.scope.eslint"),                                # no scope for this id
        ]
        for old, new, key in cases:
            with self.subTest(value=new):
                self.assertRejects(edited(old, new), key)

    def test_listed_invocations_are_checks(self):
        cfg = config.load(SAMPLE_PATH)
        cases = [
            ("pytest", "python-suite"),
            ("pytest -q", "python-suite"),
            ("python -m pytest", "python-suite"),
            ("uv run pytest", "python-suite"),
            ("npm test", "js-suite"),
            ("mypy src", "types"),
            ("ruff check .", "lint"),
            ("  pytest -q\t", "python-suite"),   # surrounding whitespace is stripped
            ("pytest\n", "python-suite"),
        ]
        for command, check_id in cases:
            with self.subTest(command=command):
                self.assertEqual(cfg.check_for(command), check_id)

    def test_aliases_name_a_check_that_exists(self):
        cases = [
            ('"the suite"  = "python-suite"', '"the suite" = "typo-suite"',
             'checks.aliases."the suite"'),
            ('"the suite"  = "python-suite"', '" the suite" = "python-suite"',
             'checks.aliases." the suite"'),
            ('"the suite"  = "python-suite"', '"THE TESTS" = "python-suite"',
             'checks.aliases."THE TESTS"'),          # "the tests" already, case ignored
            ('"the suite"  = "python-suite"', '"pytest -q" = "python-suite"',
             'checks.aliases."pytest -q"'),          # already an invocation
        ]
        for old, new, key in cases:
            with self.subTest(value=new):
                self.assertRejects(edited(old, new), key)

    def test_the_sample_aliases_load_lowercased(self):
        cfg = config.load(SAMPLE_PATH)
        self.assertEqual(dict(cfg.aliases), {"unit test": "python-suite",
                                             "unit tests": "python-suite",
                                             "the tests": "python-suite",
                                             "the suite": "python-suite"})

    def test_a_scope_entry_with_whitespace_is_refused(self):
        error = self.assertRejects(
            edited('python-suite = ["src/**/*.py", "tests/**/*.py"]',
                   'python-suite = ["python3 -m unittest discover"]'),
            "checks.scope.python-suite[0]")
        self.assertIn("whitespace", str(error))
        self.assertIn("[checks.scope] lists the file globs", str(error))

    def test_a_tier_glob_may_still_hold_a_space(self):
        cfg = self.load_text(small_config(low=["my docs/**"]))
        self.assertEqual(cfg.tier_for("Edit", paths=["my docs/a.md"]),
                         config.TierMatch(LOW, "my docs/**"))

    def test_pytest_version_is_not_a_check(self):
        self.assertIsNone(config.load(SAMPLE_PATH).check_for("pytest --version"))

    def test_unlisted_invocations_are_not_checks(self):
        cfg = config.load(SAMPLE_PATH)
        for command in ["pytest -q -x", "pytest  -q", "pytest tests/test_one.py",
                        "npm test -- --watch", "python3 -m pytest", "PYTHONPATH=src pytest",
                        "timeout 60 pytest", "pytest -q || true", "cd src && pytest",
                        "pytest | tee log", "pytest -q\nrm x", "ruff check src", "Pytest", ""]:
            with self.subTest(command=command):
                self.assertIsNone(cfg.check_for(command))


class TierPrecedenceTest(ConfigTest):
    def setUp(self):
        super().setUp()
        self.cfg = config.load(SAMPLE_PATH)

    def assertTier(self, tier, rule, tool, **action):
        self.assertEqual(self.cfg.tier_for(tool, **action), config.TierMatch(tier, rule))

    def test_paths(self):
        cases = [
            ("migrations/0007_add_index.sql", HUMAN, "migrations/**"),
            ("migrations/README.md", HUMAN, "migrations/**"),  # HUMAN beats LOW
            ("deploy/prod.yaml", HUMAN, "deploy/**"),
            ("docs/guide.txt", LOW, "docs/**"),
            ("docs/guide.md", LOW, "docs/**"),                 # first LOW entry in file order
            ("README.md", LOW, "**/*.md"),
            ("src/engine.py", REVIEW, None),                   # LOW beats only the default
            ("Docs/guide.txt", REVIEW, None),                  # case-sensitive
        ]
        for path, tier, rule in cases:
            with self.subTest(path=path):
                self.assertTier(tier, rule, "Edit", paths=[path])

    def test_bash_commands(self):
        cases = [
            ("git push origin main", HUMAN, "Bash(git push*)"),
            ("npm test && git push", HUMAN, "Bash(git push*)"),
            ("timeout 60 git push", HUMAN, "Bash(git push*)"),
            ("echo $(git push)", HUMAN, "Bash(git push*)"),
            ("rm -rf build", HUMAN, "Bash(*rm -rf*)"),
            ("git push -f; rm -rf /tmp/x", HUMAN, "Bash(git push*)"),  # file order
            ("pytest -q", REVIEW, None),
            ("git status", REVIEW, None),
        ]
        for command, tier, rule in cases:
            with self.subTest(command=command):
                self.assertTier(tier, rule, "Bash", command=command)

    def test_bash_entries_apply_only_to_bash(self):
        self.assertTier(REVIEW, None, "PowerShell", command="git push")

    def test_several_paths_take_the_most_severe(self):
        self.assertTier(HUMAN, "migrations/**", "Edit", paths=["docs/a.md", "migrations/x.sql"])
        self.assertTier(REVIEW, None, "Edit", paths=["docs/a.md", "src/x.py"])

    def test_low_needs_every_segment_covered(self):
        cfg = self.load_text(small_config(low=["Bash(ls *)", "Bash(echo *)"]))
        self.assertEqual(cfg.tier_for("Bash", command="ls -la"), config.TierMatch(LOW, "Bash(ls *)"))
        self.assertEqual(cfg.tier_for("Bash", command="echo hi && ls"),
                         config.TierMatch(LOW, "Bash(ls *)"))
        self.assertEqual(cfg.tier_for("Bash", command="ls && rm x"), config.TierMatch(REVIEW, None))
        self.assertEqual(cfg.tier_for("Bash", command="FOO=1 ls"), config.TierMatch(REVIEW, None))

    def test_paths_must_be_normalised_project_relative(self):
        for path in ["/abs/x.py", "./x.py", "a/../b.py", "a//b.py", "a\\b.py", "", "src/"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.cfg.tier_for("Edit", paths=[path])

    def test_permission_rule_wildcards(self):
        cases = [
            ("ls *", "ls", True), ("ls *", "ls -la", True), ("ls *", "lsof", False),
            ("ls*", "lsof", True),
            ("ls:*", "ls", True), ("ls:*", "ls -la", True), ("ls:*", "lsof", False),
            ("git log * main", "git log --oneline main", True),
            ("git log * main", "git log main", False),
            ("npm run build", "npm run build", True),
            ("npm run build", "npm run build --watch", False),
            ("* --version", "node --version", True),
            ("* --help *", "npm --help x", True), ("* --help *", "npm --help", False),
            ("a?c", "abc", False), ("a?c", "a?c", True),        # only '*' is a wildcard
        ]
        for pattern, command, matches in cases:
            with self.subTest(pattern=pattern, command=command):
                cfg = self.load_text(small_config(low=[f"Bash({pattern})"]))
                self.assertEqual(cfg.tier_for("Bash", command=command).tier == LOW, matches)


class GlobTest(ConfigTest):
    def test_glob_semantics(self):
        cases = [
            ("**/*.md", "README.md", True), ("**/*.md", "a/b/c.md", True),
            ("*.md", "README.md", True), ("*.md", "docs/a.md", False),
            ("docs/**", "docs/a", True), ("docs/**", "docs/a/b", True),
            ("docs/**", "docs", False), ("docs/**", "docsx/a", False),
            ("src/**/*.py", "src/a.py", True), ("src/**/*.py", "src/x/y/a.py", True),
            ("src/**/*.py", "src/a.pyc", False), ("src/*.py", "src/x/a.py", False),
            ("docs/[!_]*.md", "docs/a.md", True), ("docs/[!_]*.md", "docs/_a.md", False),
            ("?.txt", "a.txt", True), ("?.txt", "ab.txt", False),
            ("**", "a/b", True), ("**/*", ".github/ci.yml", True),
            ("a[+-0]b", "a+b", True), ("a[+-0]b", "a/b", False),  # '/' is in +-0
        ]
        for glob, path, matches in cases:
            with self.subTest(glob=glob, path=path):
                text = small_config({"x": ["x"]}).replace('x = ["**/*"]',
                                                          f"x = [{json.dumps(glob)}]")
                cfg = self.load_text(text)
                self.assertEqual(cfg.scopes["x"][0].matches(path), matches)


if __name__ == "__main__":
    unittest.main()
