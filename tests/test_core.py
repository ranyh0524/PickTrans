import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import config as config_module
from app.cache import _key
from app.config import Config, DEFAULTS
from app.formula import build_rich_html
from app.hotkey import _parse_combo
from app.updater import _validated_web_url


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "config.json")
        self.patches = (
            patch.object(config_module, "config_dir", return_value=self.temp_dir.name),
            patch.object(config_module, "config_path", return_value=self.path),
        )
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_non_object_json_falls_back_to_defaults(self):
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump([], file)

        config = Config()

        self.assertEqual(config.get("model"), DEFAULTS["model"])

    def test_invalid_values_are_ignored_or_clamped(self):
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({
                "fixed_target": "invalid",
                "selection_enabled": "yes",
                "card_font_size": 99,
            }, file)

        config = Config()

        self.assertEqual(config.get("fixed_target"), "zh")
        self.assertIs(config.get("selection_enabled"), True)
        self.assertEqual(config.get("card_font_size"), 20)

    def test_failed_persist_does_not_publish_partial_config(self):
        config = Config()
        original = config.snapshot()

        with patch.object(config, "_write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                config.update({"model": "new-model"}, persist=True)

        self.assertEqual(config.snapshot(), original)

    def test_persist_uses_complete_valid_snapshot(self):
        config = Config()
        config.update({"model": "new-model"}, persist=True)

        with open(self.path, "r", encoding="utf-8") as file:
            saved = json.load(file)
        self.assertEqual(saved["model"], "new-model")
        self.assertFalse(os.path.exists(self.path + ".tmp"))


class FormulaTests(unittest.TestCase):
    def test_currency_is_not_treated_as_formula(self):
        self.assertIsNone(build_rich_html("Prices: $5, $10"))
        self.assertIsNone(build_rich_html("Range: $5-$10"))
        self.assertIsNone(build_rich_html("Only $5$ today"))

    def test_latex_is_still_rendered(self):
        with patch("app.formula.render_formula_png", return_value=b"png"):
            rich = build_rich_html("Value: $x_i$")
        self.assertIsNotNone(rich)
        html_text, images = rich
        self.assertIn('<img src="formula0">', html_text)
        self.assertEqual(images, {"formula0": b"png"})

    def test_escaped_dollars_are_left_as_text(self):
        self.assertIsNone(build_rich_html(r"Price: \$5 and \$10"))


class HotkeyTests(unittest.TestCase):
    def test_valid_combo(self):
        self.assertEqual(_parse_combo("ctrl+alt+y"), (0x0003, ord("Y")))

    def test_multiple_main_keys_are_rejected(self):
        self.assertIsNone(_parse_combo("ctrl+a+b"))
        self.assertIsNone(_parse_combo("ctrl+ctrl+a"))
        self.assertIsNone(_parse_combo("ctrl+unknown"))


class CacheTests(unittest.TestCase):
    def test_api_base_is_part_of_cache_key(self):
        common = ("hello", "en", "zh", "same-model", 0.3)
        first = _key(*common, "https://first.example/v1")
        second = _key(*common, "https://second.example/v1")
        self.assertNotEqual(first, second)


class UpdaterTests(unittest.TestCase):
    def test_https_and_local_http_are_allowed(self):
        self.assertEqual(
            _validated_web_url("https://example.com/version.json", "地址"),
            "https://example.com/version.json",
        )
        self.assertEqual(
            _validated_web_url("http://127.0.0.1/version.json", "地址"),
            "http://127.0.0.1/version.json",
        )

    def test_unsafe_schemes_are_rejected(self):
        for url in ("http://example.com/version.json", "file:///tmp/version.json", "calc:"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _validated_web_url(url, "地址")


if __name__ == "__main__":
    unittest.main()
