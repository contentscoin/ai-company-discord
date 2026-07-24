"""Unit tests for companyctl pure logic (no network). Run: python3 -m unittest discover -s tests"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "companyctl", REPO_ROOT / "scripts" / "companyctl.py"
)
companyctl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(companyctl)

TEMPLATE = json.loads((REPO_ROOT / "templates" / "company.discord.json").read_text())


class ValidateTests(unittest.TestCase):
    def test_shipped_template_is_valid(self):
        self.assertEqual(companyctl.validate(TEMPLATE, REPO_ROOT), [])

    def test_bad_category_is_reported(self):
        cfg = json.loads(json.dumps(TEMPLATE))
        cfg["discord"]["channels"][0]["category"] = "nope"
        errors = companyctl.validate(cfg, REPO_ROOT)
        self.assertTrue(any("not in discord.categories" in e for e in errors))

    def test_missing_soul_is_reported(self):
        cfg = json.loads(json.dumps(TEMPLATE))
        cfg["roles"][0]["hermesProfile"] = "ghost"
        errors = companyctl.validate(cfg, REPO_ROOT)
        self.assertTrue(any("no SOUL.md" in e for e in errors))

    def test_bad_access_token_is_reported(self):
        cfg = json.loads(json.dumps(TEMPLATE))
        cfg["discord"]["channels"][0]["access"] = ["board", "nobody"]
        errors = companyctl.validate(cfg, REPO_ROOT)
        self.assertTrue(any("nobody" in e for e in errors))


class BootstrapPlanTests(unittest.TestCase):
    def test_empty_guild_creates_everything(self):
        plan = companyctl.compute_bootstrap_plan(TEMPLATE, set(), [])
        self.assertEqual(plan["roles_to_create"], companyctl.SERVER_ROLES)
        self.assertEqual(
            plan["categories_to_create"], TEMPLATE["discord"]["categories"]
        )
        self.assertEqual(
            len(plan["channels_to_create"]), len(TEMPLATE["discord"]["channels"])
        )

    def test_fully_provisioned_guild_is_idempotent(self):
        existing_roles = set(companyctl.SERVER_ROLES)
        existing_channels = [
            {"name": c, "type": companyctl.CH_CATEGORY}
            for c in TEMPLATE["discord"]["categories"]
        ] + [
            {"name": ch["name"], "type": companyctl.CH_TEXT}
            for ch in TEMPLATE["discord"]["channels"]
        ]
        plan = companyctl.compute_bootstrap_plan(
            TEMPLATE, existing_roles, existing_channels
        )
        self.assertEqual(plan["roles_to_create"], [])
        self.assertEqual(plan["categories_to_create"], [])
        self.assertEqual(plan["channels_to_create"], [])

    def test_partial_guild_creates_only_missing(self):
        existing_channels = [
            {"name": "board", "type": companyctl.CH_CATEGORY},
            {"name": "board-you", "type": companyctl.CH_TEXT},
        ]
        plan = companyctl.compute_bootstrap_plan(
            TEMPLATE, {"Board"}, existing_channels
        )
        self.assertNotIn("board", plan["categories_to_create"])
        self.assertNotIn("Board", plan["roles_to_create"])
        created_names = {c["name"] for c in plan["channels_to_create"]}
        self.assertNotIn("board-you", created_names)
        self.assertIn("standup", created_names)

    def test_narrower_access_is_noted(self):
        plan = companyctl.compute_bootstrap_plan(TEMPLATE, set(), [])
        noted = {n["name"] for n in plan["narrower_access"]}
        # #dev = cto/loop/critic (narrower than exec); #standup = exec (not noted)
        self.assertIn("dev", noted)
        self.assertNotIn("standup", noted)


class DoctorTests(unittest.TestCase):
    def _profile(self, base: Path, name: str, token: str) -> None:
        pdir = base / "profiles" / name
        pdir.mkdir(parents=True)
        (pdir / "SOUL.md").write_text("soul")
        (pdir / "config.yaml").write_text("discord:\n  require_mention: true\n")
        (pdir / ".env").write_text(f"DISCORD_BOT_TOKEN={token}\n")

    def test_duplicate_token_is_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._profile(home, "ceo", "AAA")
            self._profile(home, "cto", "AAA")  # same token = footgun
            cfg = {
                "roles": [
                    {"id": "ceo", "hermesProfile": "ceo"},
                    {"id": "cto", "hermesProfile": "cto"},
                ]
            }
            rows = companyctl.doctor_offline(cfg, home)
            self.assertTrue(
                any(l == "FAIL" and "shared DISCORD_BOT_TOKEN" in m for l, m in rows)
            )

    def test_distinct_tokens_no_share_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._profile(home, "ceo", "AAA")
            self._profile(home, "cto", "BBB")
            cfg = {
                "roles": [
                    {"id": "ceo", "hermesProfile": "ceo"},
                    {"id": "cto", "hermesProfile": "cto"},
                ]
            }
            rows = companyctl.doctor_offline(cfg, home)
            self.assertFalse(any("shared DISCORD_BOT_TOKEN" in m for _, m in rows))

    def test_duplicate_discord_key_is_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pdir = home / "profiles" / "ceo"
            pdir.mkdir(parents=True)
            (pdir / "SOUL.md").write_text("s")
            (pdir / ".env").write_text("DISCORD_BOT_TOKEN=X\n")
            (pdir / "config.yaml").write_text(
                "discord:\n  require_mention: true\ndiscord:\n  auto_thread: true\n"
            )
            cfg = {"roles": [{"id": "ceo", "hermesProfile": "ceo"}]}
            rows = companyctl.doctor_offline(cfg, home)
            self.assertTrue(any("duplicate top-level `discord:`" in m for _, m in rows))


class StandupTests(unittest.TestCase):
    def test_render_includes_date_and_mentions(self):
        body = companyctl.render_standup("2026-07-24", ["CTO", "LOOP", "GROWTH"])
        self.assertIn("2026-07-24", body)
        self.assertIn("@CTO", body)
        self.assertIn("@GROWTH", body)


if __name__ == "__main__":
    unittest.main()
