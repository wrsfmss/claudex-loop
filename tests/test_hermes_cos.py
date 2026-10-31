"""Contract tests for the claudex-cos Hermes plugin; no Hermes runtime or model calls."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "integrations/hermes/claudex-cos"
SPEC = importlib.util.spec_from_file_location("claudex_cos", PLUGIN / "__init__.py")
cos = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cos)


class FakeCtx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler, description):
        self.tools[name] = (toolset, schema, handler, description)


def call(ctx, name, **args):
    return json.loads(ctx.tools[name][2](args))


class TriageTests(unittest.TestCase):
    def test_internal_reads_are_act(self):
        for task in ("Summarise today's unread mail", "Research three vendors for the quote", "Draft a reply to the landlord"):
            with self.subTest(task=task):
                self.assertEqual(cos.triage(task)["tier"], "act")

    def test_drafting_and_sending_together_is_ask(self):
        self.assertEqual(cos.triage("Draft a reply and send it to the landlord")["tier"], "ask")

    def test_external_and_irreversible_need_approval(self):
        for task in ("Send the proposal to the client", "Delete the old invoices", "Pay the supplier invoice",
                     "Schedule a meeting with the board attendees", "Set up a recurring weekly routine"):
            with self.subTest(task=task):
                result = cos.triage(task)
                self.assertEqual(result["tier"], "ask")
                self.assertTrue(result["requires_approval"])

    def test_prohibited_requests_are_never(self):
        for task in ("Save my password in plaintext in notes", "Fabricate the source citations for the report"):
            with self.subTest(task=task):
                result = cos.triage(task)
                self.assertEqual(result["tier"], "never")
                self.assertEqual(result["route"], "decline")

    def test_routing(self):
        self.assertEqual(cos.triage("Implement the billing service integration")["route"], "claudex-loop")
        self.assertEqual(cos.triage("Fix a typo in the plugin readme")["route"], "self")
        self.assertEqual(cos.triage("Give me a second opinion on the roadmap")["route"], "claudex-route")
        self.assertEqual(cos.triage("What time is it in Belfast")["route"], "self")

    def test_design_is_not_sign(self):
        self.assertEqual(cos.triage("Review the design notes")["tier"], "act")


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeCtx()
        cos.register(self.ctx)

    def test_registers_declared_tools(self):
        declared = [line.split("- ")[1] for line in (PLUGIN / "plugin.yaml").read_text().splitlines() if line.startswith("  - ")]
        self.assertEqual(sorted(self.ctx.tools), sorted(declared))
        for name, (toolset, schema, _handler, description) in self.ctx.tools.items():
            self.assertEqual(schema["name"], name)
            self.assertEqual(toolset, "claudex_cos")
            self.assertTrue(description)

    def test_triage_requires_task(self):
        self.assertFalse(call(self.ctx, "claudex_cos_triage")["success"])
        self.assertEqual(call(self.ctx, "claudex_cos_triage", task="Send the invoice")["tier"], "ask")

    def test_delegate_gates(self):
        refused = call(self.ctx, "claudex_cos_delegate", task="Send the invoice to the client")
        self.assertFalse(refused["success"])
        self.assertFalse(refused["delegated"])
        self.assertIn("approval", refused["error"])
        never = call(self.ctx, "claudex_cos_delegate", task="Fabricate the data for the report", approved=True)
        self.assertFalse(never["success"])
        self.assertFalse(call(self.ctx, "claudex_cos_delegate")["success"])

    def test_approved_ask_task_reaches_lifecycle(self):
        # Outside Hermes the lifecycle import fails, which proves the approval gate was passed.
        result = call(self.ctx, "claudex_cos_delegate", task="Send the invoice to the client", approved=True)
        self.assertNotIn("approval", result.get("error", ""))
        self.assertIn("unavailable", result["error"])

    def test_brief_prefers_user_override(self):
        with tempfile.TemporaryDirectory() as home:
            override = Path(home) / "claudex-cos"
            override.mkdir()
            (override / "doctrine.md").write_text("custom doctrine", encoding="utf-8")
            with patch.dict(os.environ, {"HERMES_HOME": home}):
                self.assertEqual(call(self.ctx, "claudex_cos_brief")["doctrine"], "custom doctrine")
            with patch.dict(os.environ, {"HERMES_HOME": home + "/missing"}):
                self.assertIn("Autonomy tiers", call(self.ctx, "claudex_cos_brief")["doctrine"])


if __name__ == "__main__":
    unittest.main()
