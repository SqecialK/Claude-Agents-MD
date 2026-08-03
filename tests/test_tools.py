import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.job_parser import JobUrlError, build_apply_url, extract_job_id
from tools.solution_identifier import identify_solution
from tools.proposal_content import render_cover_letter, generate_vsl_script
from tools.infographic import generate_infographic_url
from tools.sheets_client import build_row, SHEET_COLUMNS
from operations.generate_proposal import generate_proposal


class JobParserTests(unittest.TestCase):
    def test_extract_job_id(self):
        self.assertEqual(extract_job_id("https://www.upwork.com/jobs/~021234567890"), "021234567890")

    def test_build_apply_url(self):
        url = build_apply_url("https://www.upwork.com/jobs/~021234567890")
        self.assertEqual(url, "https://www.upwork.com/nx/proposals/job/~021234567890/apply/")

    def test_missing_job_id_raises(self):
        with self.assertRaises(JobUrlError):
            extract_job_id("https://www.upwork.com/jobs/no-id-here")


class SolutionIdentifierTests(unittest.TestCase):
    def test_ai_lead_generation_detected(self):
        solution = identify_solution("Lead gen with Apollo", "Automate outreach using Apollo and Lindy")
        self.assertEqual(solution["name"], "AI Lead Generation")

    def test_ai_receptionist_detected(self):
        solution = identify_solution("Build AI Chatbot", "Need an AI receptionist for customer service")
        self.assertEqual(solution["name"], "AI Receptionist")

    def test_default_fallback(self):
        solution = identify_solution("Random project", "Nothing matches any keyword here")
        self.assertEqual(solution["name"], "Workflow Automation")


class ProposalContentTests(unittest.TestCase):
    def setUp(self):
        self.solution = identify_solution("Workflow help", "Connect Zapier and Google Sheets")

    def test_cover_letter_contains_bio_and_placeholder(self):
        letter = render_cover_letter("Workflow help", self.solution)
        self.assertIn("Matt Kerkhoff", letter)
        self.assertIn("Workflow Automation system", letter)
        self.assertIn("[ADD YOUR LOOM RECORDING LINK HERE]", letter)

    def test_vsl_script_mentions_infographic_and_cta(self):
        script = generate_vsl_script("Workflow help", "We need Zapier automation for our order process", self.solution)
        self.assertIn("infographic", script.lower())
        self.assertIn("call", script.lower())


class InfographicTests(unittest.TestCase):
    def test_round_trip_base64(self):
        mermaid_source = "flowchart TB\nA-->B"
        url = generate_infographic_url(mermaid_source)
        self.assertTrue(url.startswith("https://mermaid.ink/img/"))
        encoded = url.rsplit("/", 1)[-1]
        decoded = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        self.assertEqual(decoded, mermaid_source)


class SheetsClientTests(unittest.TestCase):
    def test_build_row_shape_and_hyperlinks(self):
        proposal = {
            "job_title": "Test Job",
            "apply_url": "https://www.upwork.com/nx/proposals/job/~123/apply/",
            "cover_letter": "Hi!",
            "vsl_script": "Hey there.",
            "infographic_url": "https://mermaid.ink/img/abc",
        }
        row = build_row(proposal)
        self.assertEqual(len(row), len(SHEET_COLUMNS))
        self.assertIn("=HYPERLINK(", row[1])
        self.assertIn("=HYPERLINK(", row[4])
        self.assertEqual(row[5], "New")


class EndToEndTests(unittest.TestCase):
    def test_generate_proposal_full_pipeline(self):
        proposal = generate_proposal(
            "AI Automation Specialist for Lead Generation",
            "https://www.upwork.com/jobs/~021234567890",
            "Looking for someone to build an automated outreach system using Apollo and Lindy.",
        )
        self.assertEqual(proposal["solution_category"], "AI Lead Generation")
        self.assertEqual(proposal["apply_url"], "https://www.upwork.com/nx/proposals/job/~021234567890/apply/")
        self.assertIn("Matt Kerkhoff", proposal["cover_letter"])
        self.assertTrue(proposal["infographic_url"].startswith("https://mermaid.ink/img/"))


if __name__ == "__main__":
    unittest.main()
