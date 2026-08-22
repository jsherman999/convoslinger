"""Regression tests for the parts that quietly rot: parsing and rendering.

    python3 -m unittest discover -s tests
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from convoslinger import manifest as mf
from convoslinger import markdown, parse, scrub


class Markdown(unittest.TestCase):
    def test_escapes_html(self):
        self.assertIn("&lt;script&gt;", markdown.render("<script>alert(1)</script>"))

    def test_code_fence_is_not_interpreted(self):
        out = markdown.render("```js\nconst a = **not bold**;\n```")
        self.assertIn("**not bold**", out)
        self.assertIn('class="language-js"', out)

    def test_nested_list_stops_at_the_next_block(self):
        out = markdown.render("- one\n  - deep\n\nA paragraph.\n")
        self.assertEqual(out.count("<ul>"), 2)
        self.assertTrue(out.endswith("<p>A paragraph.</p>"))

    def test_table(self):
        out = markdown.render("| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<th>a</th>", out)
        self.assertIn("<td>2</td>", out)

    def test_dangerous_url_is_neutralised(self):
        self.assertIn('href="#"', markdown.inline("[x](javascript:alert*1*)"))

    def test_link_and_emphasis(self):
        out = markdown.inline("see [docs](https://example.com) for **more**")
        self.assertIn('<a href="https://example.com"', out)
        self.assertIn("<strong>more</strong>", out)


class Parsing(unittest.TestCase):
    def test_speaker_markers(self):
        turns = parse.parse("Human: hi\n\nAssistant: hello\n\nHuman: bye")
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user"])

    def test_prose_is_not_mistaken_for_a_marker(self):
        turns = parse.parse("You should never do that.\nClaude is fine though.")
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["role"], "note")

    def test_markers_inside_code_are_ignored(self):
        turns = parse.parse('Human: run this\n\n```\nUser: fake\nAssistant: fake\n```\n\nAssistant: ok')
        self.assertEqual([t["role"] for t in turns], ["user", "assistant"])

    def test_jsonl_session(self):
        lines = [
            {"type": "user", "message": {"role": "user", "content": "build it"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "on it"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "make"}},
            ]}},
        ]
        turns = parse.parse("\n".join(json.dumps(l) for l in lines), "s.jsonl")
        self.assertEqual([t["kind"] for t in turns], ["md", "md", "tool"])
        self.assertEqual(turns[2]["label"], "Bash")

    def test_malformed_jsonl_lines_are_skipped(self):
        text = '{"type":"user","message":{"role":"user","content":"a"}}\nnot json\n'
        self.assertEqual(len(parse.parse(text, "s.jsonl")), 1)

    def test_synopsis_does_not_repeat_the_title(self):
        turns = parse.parse("Human: Fix the build. It fails on CI only.\n\nAssistant: ok")
        title = parse.auto_title(turns)
        self.assertEqual(title, "Fix the build.")
        self.assertNotIn("Fix the build", parse.auto_synopsis(turns, skip=title))


class Secrets(unittest.TestCase):
    def test_keys_are_redacted(self):
        text, hits = scrub.scrub("token sk-ant-api03-" + "A" * 24)
        self.assertIn("[redacted]", text)
        self.assertEqual(hits[0]["kind"], "Anthropic API key")

    def test_ordinary_text_is_left_alone(self):
        text = "The password reset flow is broken."
        self.assertEqual(scrub.scrub(text)[0], text)


class Manifest(unittest.TestCase):
    def test_ids_are_unique(self):
        m = mf.empty()
        first = mf.make_id(m, "Same title", "2026-01-01")
        m["convos"].append(mf.normalize({"id": first, "title": "Same title"}))
        self.assertNotEqual(first, mf.make_id(m, "Same title", "2026-01-01"))

    def test_display_order_pins_first_then_newest(self):
        m = mf.empty()
        m["convos"] = [
            mf.normalize({"id": "a", "date": "2026-01-01", "pinned": True}),
            mf.normalize({"id": "b", "date": "2026-03-01"}),
            mf.normalize({"id": "c", "date": "2026-02-01", "visible": False}),
        ]
        self.assertEqual([c["id"] for c in mf.display_order(m)], ["a", "b"])
        self.assertEqual([c["id"] for c in mf.display_order(m, True)], ["a", "b", "c"])

    def test_unknown_fields_survive_a_round_trip(self):
        self.assertEqual(mf.normalize({"id": "x", "note": "keep me"})["note"], "keep me")


if __name__ == "__main__":
    unittest.main()
