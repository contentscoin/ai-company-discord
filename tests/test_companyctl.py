"""Unit tests for companyctl pure logic (no network). Run: python3 -m unittest discover -s tests"""

import argparse
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

TEMPLATE = json.loads((REPO_ROOT / "templates" / "company.discord.json").read_text(encoding="utf-8"))


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
        (pdir / "SOUL.md").write_text("soul", encoding="utf-8")
        (pdir / "config.yaml").write_text("discord:\n  require_mention: true\n", encoding="utf-8")
        (pdir / ".env").write_text(f"DISCORD_BOT_TOKEN={token}\n", encoding="utf-8")

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
            (pdir / "SOUL.md").write_text("s", encoding="utf-8")
            (pdir / ".env").write_text("DISCORD_BOT_TOKEN=X\n", encoding="utf-8")
            (pdir / "config.yaml").write_text(
                "discord:\n  require_mention: true\ndiscord:\n  auto_thread: true\n",
                encoding="utf-8",
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


class ArchiveTests(unittest.TestCase):
    def test_render_minutes_chronological(self):
        msgs = [
            {"author": {"username": "CEO"}, "content": "안건 정리"},
            {"author": {"username": "CTO"}, "content": ""},  # empty skipped
            {"author": {"username": "Loop"}, "content": "DoD 통과"},
        ]
        out = companyctl.render_minutes("2026-W30 · MRR", msgs)
        self.assertIn("# 회의록 — 2026-W30 · MRR", out)
        self.assertIn("- **CEO**: 안건 정리", out)
        self.assertIn("- **Loop**: DoD 통과", out)
        self.assertNotIn("**CTO**", out)

    def test_minutes_with_token_are_flagged(self):
        secret = ".".join(["A" * 26, "B" * 6, "C" * 30])
        msgs = [{"author": {"username": "x"}, "content": f"token {secret}"}]
        minutes = companyctl.render_minutes("t", msgs)
        self.assertTrue(companyctl.scan_for_sensitive(minutes))  # would BLOCK the post

    def test_chunk_text_respects_size(self):
        chunks = companyctl.chunk_text("x" * 4100, size=1900)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(c) <= 1900 for c in chunks))

    def test_slugify(self):
        self.assertEqual(companyctl.slugify("2026-W30 · MRR 점검"), "2026-w30-mrr")


class DoctorModelHintTests(unittest.TestCase):
    def test_missing_modelhint_warns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pdir = home / "profiles" / "ceo"
            pdir.mkdir(parents=True)
            (pdir / "SOUL.md").write_text("s", encoding="utf-8")
            (pdir / "config.yaml").write_text("discord:\n", encoding="utf-8")
            (pdir / ".env").write_text("DISCORD_BOT_TOKEN=X\n", encoding="utf-8")
            cfg = {"roles": [{"id": "ceo", "hermesProfile": "ceo"}]}  # no modelHint
            rows = companyctl.doctor_offline(cfg, home)
            self.assertTrue(any("no modelHint" in m for _, m in rows))

    def test_shipped_template_roles_all_have_modelhint(self):
        self.assertTrue(all(r.get("modelHint") for r in TEMPLATE["roles"]))


# --- Regression tests for review-confirmed fixes ------------------------- #
class ValidateRobustnessTests(unittest.TestCase):
    def test_non_string_access_element_does_not_crash(self):
        for bad in ([{"role": "board"}], [["board"]]):
            cfg = json.loads(json.dumps(TEMPLATE))
            cfg["discord"]["channels"][0]["access"] = bad
            errors = companyctl.validate(cfg, REPO_ROOT)  # must not raise TypeError
            self.assertTrue(any("entries must be strings" in e for e in errors))


class SensitiveScanExtraTests(unittest.TestCase):
    def _kinds(self, text):
        return {k for _, _, k in companyctl.scan_for_sensitive(text)}

    def test_openai_project_key_detected(self):
        self.assertIn("api-key", self._kinds("sk-proj-" + "T3Blbk" + "a" * 30))

    def test_pem_private_key_detected(self):
        self.assertIn("private-key", self._kinds("-----BEGIN OPENSSH PRIVATE KEY-----"))

    def test_jwt_detected(self):
        self.assertIn("jwt", self._kinds("eyJ" + "a" * 12 + ".eyJ" + "b" * 20 + "." + "c" * 30))

    def test_slack_webhook_detected(self):
        self.assertIn("slack-webhook", self._kinds("https://hooks.slack.com/services/T0/B0/xyz"))


class DoctorRegressionTests(unittest.TestCase):
    def _profile(self, base, name, token, require_mention="true"):
        d = base / "profiles" / name
        d.mkdir(parents=True)
        (d / "SOUL.md").write_text("s", encoding="utf-8")
        (d / ".env").write_text(f"DISCORD_BOT_TOKEN={token}\n", encoding="utf-8")
        (d / "config.yaml").write_text(
            f"discord:\n  require_mention: {require_mention}\nplatform_toolsets:\n  discord: [x]\n",
            encoding="utf-8",
        )

    def test_same_profile_mapped_twice_no_false_shared_fail(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._profile(home, "ceo", "A")
            cfg = {"roles": [
                {"id": "ceo", "hermesProfile": "ceo", "modelHint": "x"},
                {"id": "chair", "hermesProfile": "ceo", "modelHint": "x"},
            ]}
            rows = companyctl.doctor_offline(cfg, home)
            self.assertFalse(any("shared DISCORD_BOT_TOKEN" in m for _, m in rows))

    def test_require_mention_false_is_fail(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._profile(home, "ceo", "A", require_mention="false")
            cfg = {"roles": [{"id": "ceo", "hermesProfile": "ceo", "modelHint": "x"}]}
            rows = companyctl.doctor_offline(cfg, home)
            self.assertTrue(any(l == "FAIL" and "require_mention is false" in m for l, m in rows))


class LifecycleTests(unittest.TestCase):
    CFG = {"roles": [
        {"id": "ceo", "hermesProfile": "ceo"},
        {"id": "cto", "hermesProfile": "cto"},
    ]}

    def test_selected_profiles_all_and_one(self):
        self.assertEqual(companyctl.selected_profiles(self.CFG, None), ["ceo", "cto"])
        self.assertEqual(companyctl.selected_profiles(self.CFG, "cto"), ["cto"])

    def test_unknown_profile_is_clean_exit(self):
        with self.assertRaises(SystemExit):
            companyctl.selected_profiles(self.CFG, "nope")

    def test_pid_alive_rejects_impossible_pids(self):
        self.assertFalse(companyctl.pid_alive(-1))
        self.assertFalse(companyctl.pid_alive(0))
        self.assertFalse(companyctl.pid_alive(None))

    @unittest.skipIf(companyctl.IS_WINDOWS, "native lifecycle is POSIX-only")
    def test_pid_alive_true_for_self(self):
        import os as _os
        self.assertTrue(companyctl.pid_alive(_os.getpid()))

    def test_pid_alive_never_probes_destructively_on_windows(self):
        """os.kill(pid, 0) TERMINATES the target on Windows, so pid_alive must
        not reach it there — a status refresh would kill every gateway."""
        import os as _os
        from unittest import mock
        with mock.patch.object(companyctl, "IS_WINDOWS", True):
            with mock.patch.object(companyctl.os, "kill") as killed:
                self.assertFalse(companyctl.pid_alive(_os.getpid()))
                killed.assert_not_called()

    def test_lifecycle_commands_refuse_to_run_on_windows(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock
        err = io.StringIO()
        with mock.patch.object(companyctl, "IS_WINDOWS", True):
            with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                companyctl.require_posix_lifecycle()
        # "could not run" per the documented contract, message on stderr
        self.assertEqual(cm.exception.code, companyctl.EXIT_CANNOT_RUN)
        self.assertIn("docker compose up -d", err.getvalue())

    def test_lifecycle_allowed_on_posix(self):
        from unittest import mock
        with mock.patch.object(companyctl, "IS_WINDOWS", False):
            companyctl.require_posix_lifecycle()  # must not raise

    @unittest.skipIf(companyctl.IS_WINDOWS, "zombies are a POSIX concept; lifecycle is POSIX-only")
    def test_zombie_is_not_alive(self):
        """A gateway whose parent exited lingers as an unreaped zombie; status
        must not count it as up."""
        import os as _os, subprocess as _sp, time as _t
        proc = _sp.Popen(["sleep", "30"], start_new_session=True,
                         stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        pid = proc.pid
        self.assertTrue(companyctl.pid_alive(pid))
        proc.kill()
        # Do NOT wait() — leaving it unreaped is exactly the zombie case.
        for _ in range(50):
            if companyctl._is_zombie(pid) or not _os.path.exists(f"/proc/{pid}"):
                break
            _t.sleep(0.05)
        self.assertFalse(companyctl.pid_alive(pid))
        proc.wait()  # clean up the test's own child

    def test_corrupt_gateway_state_is_clean_exit(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "ai-company").mkdir(parents=True)
            (home / "ai-company" / "gateways.json").write_text("{oops", encoding="utf-8")
            with self.assertRaises(SystemExit):
                companyctl.load_gateways(home)

    def test_gateway_state_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            companyctl.save_gateways(home, {"ceo": {"pid": 42}})
            self.assertEqual(companyctl.load_gateways(home)["ceo"]["pid"], 42)

    def test_gateways_are_started_with_run_not_start(self):
        """`gateway start` drives an already-installed service and returns; only
        `gateway run` is the foreground process whose pid we can track.
        Verified against hermes-agent 0.19.0."""
        from unittest import mock
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(companyctl.subprocess, "Popen") as popen:
                popen.return_value.pid = 4242
                companyctl.start_gateway(Path(tmp), "ceo")
            argv = popen.call_args[0][0]
            self.assertEqual(argv[-3:], ["ceo", "gateway", "run"])
            self.assertNotIn("start", argv)

    def test_service_delegates_to_hermes_gateway_install(self):
        """Upstream writes the systemd/launchd unit itself; emitting our own
        would compete with it."""
        self.assertFalse(hasattr(companyctl, "SYSTEMD_UNIT"))
        self.assertFalse(hasattr(companyctl, "LAUNCHD_PLIST"))


class JsonApiTests(unittest.TestCase):
    """The --json surface is the contract a script or GUI binds to."""

    def test_status_report_is_pure_data(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "profiles" / "ceo").mkdir(parents=True)
            cfg = {"roles": [{"id": "ceo", "hermesProfile": "ceo"},
                             {"id": "cto", "hermesProfile": "cto"}]}
            r = companyctl.status_report(cfg, home)
            self.assertEqual(r["profiles"], {"scaffolded": ["ceo"], "total": 2})
            self.assertIsNone(r["discordMap"])
            self.assertEqual(r["decisions"]["count"], 0)
            self.assertIsNone(r["lastStandup"])
            json.dumps(r)  # must be serializable

    def test_render_status_matches_report(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "profiles" / "ceo").mkdir(parents=True)
            cfg = {"roles": [{"id": "ceo", "hermesProfile": "ceo"}]}
            out = companyctl.render_status(companyctl.status_report(cfg, home))
            self.assertIn("1/1 scaffolded", out)
            self.assertIn("run `companyctl bootstrap`", out)

    def test_paperclip_issues_are_built_from_actions(self):
        entry = {"actions": [
            {"owner": "cto", "task": "fix the thing", "due": "2026-08-01"},
            {"owner": "growth", "task": "", "due": None},  # no task -> skipped
        ]}
        issues = companyctl.build_paperclip_issues(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["owner"], "cto")
        self.assertEqual(issues[0]["due"], "2026-08-01")

    def test_paperclip_unreachable_returns_payload_not_prints(self):
        entry = {"actions": [{"owner": "cto", "task": "ship it"}]}
        # port 1 is reliably closed
        result = companyctl.emit_paperclip(entry, "http://127.0.0.1:1")
        self.assertEqual(result["status"], "unreachable")
        self.assertEqual(len(result["issues"]), 1)
        self.assertIn("emitting issue payloads", companyctl.render_paperclip_result(result))

    def test_paperclip_no_actions(self):
        result = companyctl.emit_paperclip({"actions": []}, "http://127.0.0.1:1")
        self.assertEqual(result["status"], "no-actions")


class NetworkTimeoutTests(unittest.TestCase):
    def test_discord_request_passes_a_timeout(self):
        """Without it an unreachable host hangs the CLI (and would hang a GUI)."""
        from unittest import mock
        with mock.patch.object(companyctl.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"
            companyctl.discord_request("GET", "/users/@me", "tok")
            _, kwargs = urlopen.call_args
            self.assertIn("timeout", kwargs)
            self.assertGreater(kwargs["timeout"], 0)

    def test_discord_timeout_becomes_a_clean_error(self):
        from unittest import mock
        with mock.patch.object(companyctl.urllib.request, "urlopen", side_effect=TimeoutError()):
            with self.assertRaises(companyctl.DiscordError) as cm:
                companyctl.discord_request("GET", "/users/@me", "tok")
            self.assertIn("timed out", str(cm.exception))


class MapAndInputTests(unittest.TestCase):
    def test_corrupt_map_raises_clean_systemexit(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "ai-company").mkdir(parents=True)
            (home / "ai-company" / "discord.map.json").write_text("{bad json", encoding="utf-8")
            with self.assertRaises(SystemExit):
                companyctl.load_map(home)

    def test_missing_map_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(companyctl.load_map(Path(tmp)))

    def test_read_text_input_missing_file_exits_cannot_run(self):
        import io
        from contextlib import redirect_stderr
        ns = argparse.Namespace(file="/definitely/not/here.txt")
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            companyctl.read_text_input(ns)
        self.assertEqual(cm.exception.code, companyctl.EXIT_CANNOT_RUN)
        self.assertIn("cannot read", err.getvalue())

    def test_die_uses_the_documented_cannot_run_code(self):
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            companyctl.die("ERROR: nope")
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(err.getvalue().strip(), "ERROR: nope")


if __name__ == "__main__":
    unittest.main()
