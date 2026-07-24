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


class DecisionParserTests(unittest.TestCase):
    def setUp(self):
        self.role_map = companyctl.build_role_map(TEMPLATE)

    def test_meetings_style_block(self):
        block = (
            "DECISION:\n- 목표 상향\n- 채용 보류\n"
            "OPEN:\n- 가격 재검토\n"
            "ACTIONS:\n- @CTO : 버그 수정 (DUE: 2026-08-01)\n- @Growth: 캠페인 초안\n"
        )
        parsed = companyctl.parse_decision_block(block, self.role_map)
        self.assertEqual(parsed["decisions"], ["목표 상향", "채용 보류"])
        self.assertEqual(parsed["open"], ["가격 재검토"])
        self.assertEqual(parsed["actions"][0], {"owner": "cto", "task": "버그 수정", "due": "2026-08-01"})
        self.assertEqual(parsed["actions"][1], {"owner": "growth", "task": "캠페인 초안", "due": None})
        self.assertEqual(parsed["warnings"], [])

    def test_compact_owner_form(self):
        block = "DECISION: 스키마 확정\nOWNER: loop\nDUE: 2026-07-31\nPAPERCLIP: create-issue\n"
        parsed = companyctl.parse_decision_block(block, self.role_map)
        self.assertEqual(parsed["decisions"], ["스키마 확정"])
        self.assertEqual(parsed["actions"], [{"owner": "loop", "task": "스키마 확정", "due": "2026-07-31"}])

    def test_unresolved_owner_is_warned_not_lost(self):
        parsed = companyctl.parse_decision_block("ACTIONS:\n- @Nobody : do X\n", self.role_map)
        self.assertEqual(parsed["actions"][0]["owner"], "nobody")
        self.assertTrue(any("unresolved owner" in w for w in parsed["warnings"]))

    def test_title_and_board_resolve(self):
        rm = self.role_map
        warns: list = []
        self.assertEqual(companyctl.resolve_owner("Loop Engineer", rm, warns), "loop")
        self.assertEqual(companyctl.resolve_owner("board", rm, warns), "board")
        self.assertEqual(companyctl.resolve_owner("@CTO", rm, warns), "cto")
        self.assertEqual(warns, [])


class SensitiveScanTests(unittest.TestCase):
    # Fixtures are assembled at runtime so no secret-shaped literal lives in the
    # source file (avoids tripping push-protection on a fabricated test value).
    FAKE_DISCORD = ".".join(["A" * 26, "B" * 6, "C" * 30])
    FAKE_KEY = "sk-" + "x" * 24
    FAKE_EMAIL = "jane" + "@" + "example.com"

    def test_detects_token_key_email(self):
        text = f"note\n{self.FAKE_DISCORD}\n{self.FAKE_KEY}\n{self.FAKE_EMAIL}\n"
        kinds = {k for _, _, k in companyctl.scan_for_sensitive(text)}
        self.assertIn("discord-token", kinds)
        self.assertIn("api-key", kinds)
        self.assertIn("email", kinds)

    def test_clean_summary_has_no_findings(self):
        self.assertEqual(companyctl.scan_for_sensitive("이번 주 결정: 목표 상향, 채용 보류."), [])

    def test_findings_never_contain_secret_value(self):
        findings = companyctl.scan_for_sensitive(f"key {self.FAKE_KEY}\n")
        self.assertFalse(any(self.FAKE_KEY in str(f) for f in findings))


class DigestTests(unittest.TestCase):
    def test_render_groups_actions_by_owner(self):
        entries = [
            {"date": "2026-07-23", "decisions": ["A"], "open": [], "actions": [{"owner": "cto", "task": "t1"}]},
            {"date": "2026-07-24", "decisions": ["B"], "open": ["o1"],
             "actions": [{"owner": "growth", "task": "t2", "due": "2026-08-05"}]},
        ]
        out = companyctl.render_digest(entries, "2026-07-23", "2026-07-24")
        self.assertIn("## 결정 (2)", out)
        self.assertIn("- A", out)
        self.assertIn("### @cto", out)
        self.assertIn("### @growth", out)
        self.assertIn("(DUE: 2026-08-05)", out)


if __name__ == "__main__":
    unittest.main()
