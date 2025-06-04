import os
import unittest
from unittest.mock import patch, MagicMock, Mock, call # Added Mock and call
import json
import subprocess # Required for subprocess.TimeoutExpired
import argparse # For TestMainExecutionFlow
import runpy # For testing __main__ block

# Add src to path to allow direct import of agent
# This allows running tests from the project root (e.g., python -m unittest discover tests)
# or from the tests directory (e.g., python test_agent.py)
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# The module to be tested
import agent
import requests # For mocking requests in get_pr_details and post_pr_comment

# For mocking Gemini
try:
    import google.generativeai as genai
except ImportError:
    genai = None # Will be mocked if used

class TestURLParsing(unittest.TestCase):
    # Test cases for the URL parsing logic (which is part of get_pr_details and post_pr_comment)
    # We can test it somewhat indirectly via those functions, or directly if we refactor parsing.
    # For now, testing via get_pr_details with a dummy token that bypasses actual API calls.

    @patch('requests.get') # To prevent actual HTTP calls
    def test_valid_pr_url_parsing(self, mock_get):
        # This test focuses on whether the URL is parsed correctly to form an API URL.
        # It doesn't check the full behavior of get_pr_details, only the parsing aspect.
        valid_urls = [
            "https://github.com/owner/repo/pull/123",
            "http://github.com/owner/repo/pull/123", # Check http
            "https://www.github.com/owner/repo/pull/123", # Check www
            "https://github.com/owner-name/repo-name.with.dots/pull/456/" # Check trailing slash and hyphens/dots
        ]
        expected_api_calls = [
            "https://api.github.com/repos/owner/repo/pulls/123",
            "https://api.github.com/repos/owner/repo/pulls/123",
            "https://api.github.com/repos/owner/repo/pulls/123",
            "https://api.github.com/repos/owner-name/repo-name.with.dots/pulls/456"
        ]

        for i, url in enumerate(valid_urls):
            with self.subTest(url=url):
                # Mock requests.get to avoid actual calls and focus on URL formation
                mock_response_main = Mock()
                mock_response_main.status_code = 200
                mock_response_main.json.return_value = {"title": "T", "body": "B"}

                mock_response_diff = Mock()
                mock_response_diff.status_code = 200
                mock_response_diff.text = "diff"

                mock_get.side_effect = [mock_response_main, mock_response_diff]

                try:
                    # Using a special token that get_pr_details might recognize to skip some logic,
                    # or just a dummy one. If SIMULATE_SUCCESSFUL_PR_FETCH is active, it will bypass parsing.
                    # So, use a generic dummy token here for parsing tests.
                    # This token should NOT be "SIMULATE_SUCCESSFUL_PR_FETCH" for this test.
                    agent.get_pr_details(url, "dummy_token_for_url_parsing_focus")
                except ValueError as e:
                    # We expect parsing to succeed and then potentially fail at mock_get if not set up,
                    # but an "Invalid PR URL" error here means parsing itself failed.
                    if "Invalid PR URL" in str(e):
                        self.fail(f"URL parsing failed for valid URL {url}: {e}")
                except Exception:
                    # Other exceptions might occur if mocks aren't perfectly set up for full run,
                    # but for URL parsing focus, we only care about the API call argument.
                    pass

                # Check that the first call to requests.get (for main PR details) used the correct API URL
                self.assertTrue(mock_get.called, f"requests.get was not called for {url}")
                if mock_get.call_args_list: # Ensure it was called
                    # The first call is for PR details
                    actual_called_url = mock_get.call_args_list[0][0][0]
                    self.assertEqual(actual_called_url, expected_api_calls[i],
                                     f"Incorrect API URL for {url}. Expected {expected_api_calls[i]}, got {actual_called_url}")

                mock_get.reset_mock() # Reset mock for the next iteration in the loop

    def test_invalid_pr_url_parsing(self):
        invalid_urls = [
            "https://github.com/owner/repo/pulls/123",       # "pulls" instead of "pull"
            "https://github.com/owner/repo/pull/not_a_number", # Non-numeric PR number
            "https://github.com/owner/repo/123",              # Missing "pull" segment
            "https://example.com/owner/repo/pull/123",        # Not a github.com URL (as per current strict parsing)
            "ftp://github.com/owner/repo/pull/123",          # Wrong scheme
            "https://github.com/ownerrepo/pull/123",          # Missing repo part of owner/repo
            "https://github.com/pull/123",                    # Missing owner/repo
            "just_a_string"
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError, msg=f"Processing {url} did not raise ValueError for invalid format."):
                    # As above, using a dummy token that doesn't trigger simulation
                    agent.get_pr_details(url, "dummy_token_for_parsing_test")


class TestGetPrDetails(unittest.TestCase):
    @patch('requests.get')
    def test_get_pr_details_success(self, mock_get):
        mock_response_main = Mock()
        mock_response_main.status_code = 200
        mock_response_main.json.return_value = {
            "title": "Test PR Title",
            "body": "This is the PR body.",
            "user": {"login": "testuser"}
        }

        mock_response_diff = Mock()
        mock_response_diff.status_code = 200
        mock_response_diff.text = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"

        mock_get.side_effect = [mock_response_main, mock_response_diff]

        pr_details = agent.get_pr_details("https://github.com/owner/repo/pull/1", "fake_token")

        self.assertEqual(pr_details["title"], "Test PR Title")
        self.assertEqual(pr_details["body"], "This is the PR body.")
        self.assertEqual(pr_details["diff"], "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new")

        expected_headers_main = {
            "Authorization": "token fake_token",
            "Accept": "application/vnd.github.v3+json"
        }
        expected_headers_diff = {
            "Authorization": "token fake_token",
            "Accept": "application/vnd.github.v3.diff"
        }

        # Check calls to requests.get
        self.assertEqual(mock_get.call_count, 2)
        mock_get.assert_any_call("https://api.github.com/repos/owner/repo/pulls/1", headers=expected_headers_main, timeout=30)
        mock_get.assert_any_call("https://api.github.com/repos/owner/repo/pulls/1", headers=expected_headers_diff, timeout=30)

    @patch('requests.get')
    def test_get_pr_details_api_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"message": "Not Found"} # Some errors return JSON
        mock_get.return_value = mock_response
        # mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)


        with self.assertRaisesRegex(ValueError, "GitHub API request failed \(HTTP 404\): .*Not Found.*"):
            agent.get_pr_details("https://github.com/owner/repo/pull/1", "fake_token")

    @patch('requests.get')
    def test_get_pr_details_network_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("Network error")
        with self.assertRaisesRegex(ValueError, "GitHub API request failed due to a network issue: Network error"):
            agent.get_pr_details("https://github.com/owner/repo/pull/1", "fake_token")

    def test_get_pr_details_simulated_fetch(self):
        # Test the simulation logic if token is "SIMULATE_SUCCESSFUL_PR_FETCH"
        details = agent.get_pr_details("https://github.com/any/any/pull/1", "SIMULATE_SUCCESSFUL_PR_FETCH")
        self.assertEqual(details["title"], "Test PR Title")
        self.assertIn("diff --git a/test.py b/test.py", details["diff"])


@unittest.skipIf(genai is None, "google.generativeai library not available")
class TestGetGeminiReview(unittest.TestCase):
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_get_gemini_review_success(self, mock_generative_model, mock_configure):
        mock_model_instance = Mock()
        mock_response = Mock()
        mock_response.text = "This is a mock Gemini review."
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance

        pr_details = {
            "title": "Test Title",
            "body": "Test Body",
            "diff": "diff --git a/file.txt b/file.txt\n--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new"
        }
        api_key = "fake_gemini_key"
        review = agent.get_gemini_review(pr_details, api_key)

        mock_configure.assert_called_once_with(api_key=api_key)
        mock_generative_model.assert_called_once_with('gemini-1.5-pro-latest')

        # Check that generate_content was called and inspect the prompt
        mock_model_instance.generate_content.assert_called_once()
        args, _ = mock_model_instance.generate_content.call_args
        prompt = args[0]
        self.assertIn("PR Title: Test Title", prompt)
        self.assertIn("PR Body:\nTest Body", prompt)
        self.assertIn("PR Diff:\n```diff\ndiff --git a/file.txt b/file.txt", prompt)

        self.assertEqual(review, "This is a mock Gemini review.")

    def test_get_gemini_review_empty_diff(self):
        pr_details_empty_diff = {"title": "T", "body": "B", "diff": ""}
        review = agent.get_gemini_review(pr_details_empty_diff, "fake_key")
        self.assertEqual(review, "Skipping review as the PR diff is empty or not provided.")

    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_get_gemini_review_api_error(self, mock_generative_model, mock_configure):
        mock_model_instance = Mock()
        mock_model_instance.generate_content.side_effect = Exception("Gemini API Error")
        mock_generative_model.return_value = mock_model_instance

        pr_details = {"title": "T", "body": "B", "diff": "some diff"}
        review = agent.get_gemini_review(pr_details, "fake_key")
        self.assertIn("Error during Gemini API call: Exception - Gemini API Error", review)

    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_get_gemini_review_empty_response_text(self, mock_generative_model, mock_configure):
        mock_model_instance = Mock()
        mock_response = Mock()
        mock_response.text = None # Simulate empty text
        mock_response.parts = [] # Simulate no parts either
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance

        pr_details = {"title": "T", "body": "B", "diff": "some diff"}
        review = agent.get_gemini_review(pr_details, "fake_key")
        self.assertEqual(review, "Gemini API returned an empty response with no parts.")

    def test_get_gemini_review_simulated_success(self):
        # Test the simulation logic if api_key is "SIMULATE_SUCCESSFUL_GEMINI_REVIEW"
        details = {"title": "T", "body": "B", "diff": "some diff"}
        review = agent.get_gemini_review(details, "SIMULATE_SUCCESSFUL_GEMINI_REVIEW")
        self.assertEqual(review, "This is a simulated successful Gemini review. Looks good!")


class TestPostPrComment(unittest.TestCase):
    @patch('requests.post')
    @patch('builtins.print') # To capture print statements from the function
    def test_post_pr_comment_success(self, mock_print, mock_post):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_post.return_value = mock_response

        pr_url = "https://github.com/owner/repo/pull/10"
        comment_body = "Test comment"
        token = "test_github_token"

        result = agent.post_pr_comment(pr_url, comment_body, token)

        self.assertTrue(result)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.github.com/repos/owner/repo/issues/10/comments")
        self.assertIn(f'"body": "{comment_body}"', kwargs['data'])
        self.assertEqual(kwargs['headers']['Authorization'], f"token {token}")
        mock_print.assert_any_call(f"Successfully posted comment to {pr_url}. Response: 201")

    @patch('requests.post')
    @patch('builtins.print')
    def test_post_pr_comment_failure_401(self, mock_print, mock_post):
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = '{"message":"Bad credentials"}'
        mock_response.json.return_value = {"message": "Bad credentials"}
        # mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        result = agent.post_pr_comment("https://github.com/o/r/pull/1", "c", "t")
        self.assertFalse(result)
        mock_print.assert_any_call(" (Check your GITHUB_PERSONAL_ACCESS_TOKEN for necessary permissions)")

    @patch('requests.post')
    @patch('builtins.print')
    def test_post_pr_comment_failure_403(self, mock_print, mock_post):
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = '{"message":"Forbidden"}'
        mock_response.json.return_value = {"message": "Forbidden"}
        mock_post.return_value = mock_response

        result = agent.post_pr_comment("https://github.com/o/r/pull/1", "c", "t")
        self.assertFalse(result)
        mock_print.assert_any_call(" (Forbidden - check token permissions, PR might be locked, or you might not have write access)")

    @patch('requests.post')
    @patch('builtins.print')
    def test_post_pr_comment_failure_404(self, mock_print, mock_post):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = '{"message":"Not Found"}'
        mock_response.json.return_value = {"message": "Not Found"}
        mock_post.return_value = mock_response

        result = agent.post_pr_comment("https://github.com/o/r/pull/1", "c", "t")
        self.assertFalse(result)
        mock_print.assert_any_call(" (Not Found - check owner, repo, or PR number; or PR might not be found)")

    @patch('requests.post')
    @patch('builtins.print')
    def test_post_pr_comment_network_error(self, mock_print, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("Network issue")
        result = agent.post_pr_comment("https://github.com/o/r/pull/1", "c", "t")
        self.assertFalse(result)
        mock_print.assert_any_call("GitHub API request failed to post comment due to a network issue: Network issue")

    @patch('builtins.print')
    def test_post_pr_comment_invalid_url(self, mock_print):
        result = agent.post_pr_comment("invalid_url", "comment", "token")
        self.assertFalse(result)
        mock_print.assert_any_call("Error preparing to post comment: Invalid PR URL for posting comment: 'invalid_url'")


class TestMainExecutionFlow(unittest.TestCase):
    # Patches ordered from bottom-up decorator application (inside-out for args)
    # So, mock_print is the first arg to test methods after self.
    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True) # Clears os.environ for each test
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_pr_url_all_tokens_success(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print): # mock_os_environ_dict is from patch.dict
        # Setup
        mock_get_details.return_value = {"title": "T", "body": "B", "diff": "D"}
        mock_gemini_review.return_value = "This is a great PR!"
        mock_post_comment.return_value = True

        env = {"GITHUB_PERSONAL_ACCESS_TOKEN": "gh_token", "GEMINI_API_KEY": "gem_key"}
        pr_url = "http://github.com/test/repo/pull/1"

        with patch.dict(os.environ, env): # Set specific env vars for this test execution
            # Patch sys.argv for this specific runpy execution
            with patch('sys.argv', ["src/agent.py", "--pr-url", pr_url]):
                # runpy executes the module as __main__
                runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_get_details.assert_called_once_with(pr_url, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_gemini_review.assert_called_once_with(mock_get_details.return_value, env["GEMINI_API_KEY"])
        mock_post_comment.assert_called_once_with(pr_url, mock_gemini_review.return_value, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_run_agent.assert_not_called()
        mock_print.assert_any_call("Successfully posted review comment to the PR.")

    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True)
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_no_pr_url_runs_mcp_agent(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print):
        env = {"GITHUB_PERSONAL_ACCESS_TOKEN": "gh_token"}
        mock_run_agent.return_value = "MCP Agent Result"

        with patch.dict(os.environ, env):
            with patch('sys.argv', ["src/agent.py"]):
                runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_run_agent.assert_called_once() # run_agent itself will handle token check
        mock_get_details.assert_not_called()
        mock_gemini_review.assert_not_called()
        mock_post_comment.assert_not_called()
        # Check for prints from the __main__ block in agent.py
        mock_print.assert_any_call("No PR URL provided. Attempting to run default agent logic...")
        mock_print.assert_any_call("\n--- Agent Result ---")
        mock_print.assert_any_call("MCP Agent Result")

    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True)
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_pr_url_missing_github_token(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print):
        env = {"GEMINI_API_KEY": "gem_key"} # GITHUB_PERSONAL_ACCESS_TOKEN is missing
        pr_url = "http://github.com/test/repo/pull/1"

        with patch.dict(os.environ, env): # GEMINI_API_KEY is set, GITHUB_TOKEN is not
            with patch('sys.argv', ["src/agent.py", "--pr-url", pr_url]):
                 runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_get_details.assert_not_called()
        mock_gemini_review.assert_not_called()
        mock_post_comment.assert_not_called()
        mock_print.assert_any_call("\n--- Configuration Error ---")
        mock_print.assert_any_call("GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set. Cannot fetch PR details.")

    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True)
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_pr_url_missing_gemini_key(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print):
        env = {"GITHUB_PERSONAL_ACCESS_TOKEN": "gh_token"} # GEMINI_API_KEY is missing
        pr_url = "http://github.com/test/repo/pull/1"
        mock_get_details.return_value = {"title": "T", "body": "B", "diff": "D"}

        with patch.dict(os.environ, env):
            with patch('sys.argv', ["src/agent.py", "--pr-url", pr_url]):
                 runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_get_details.assert_called_once_with(pr_url, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_gemini_review.assert_not_called()
        mock_post_comment.assert_not_called()
        mock_print.assert_any_call("\n--- Gemini Configuration Error ---")
        mock_print.assert_any_call("GEMINI_API_KEY environment variable not set. Cannot get PR review.")

    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True)
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_pr_url_get_details_fails(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print):
        env = {"GITHUB_PERSONAL_ACCESS_TOKEN": "gh_token", "GEMINI_API_KEY": "gem_key"}
        pr_url = "http://github.com/test/repo/pull/1"
        mock_get_details.side_effect = ValueError("Failed to fetch PR details")

        with patch.dict(os.environ, env):
            with patch('sys.argv', ["src/agent.py", "--pr-url", pr_url]):
                 runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_get_details.assert_called_once_with(pr_url, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_gemini_review.assert_not_called()
        mock_post_comment.assert_not_called()
        mock_print.assert_any_call("\n--- Error Fetching PR Details ---")
        mock_print.assert_any_call("Failed to fetch PR details")

    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True)
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_pr_url_gemini_review_side_effect_error(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print):
        env = {"GITHUB_PERSONAL_ACCESS_TOKEN": "gh_token", "GEMINI_API_KEY": "gem_key"}
        pr_url = "http://github.com/test/repo/pull/1"
        mock_get_details.return_value = {"title": "T", "body": "B", "diff": "D"}
        mock_gemini_review.side_effect = RuntimeError("Gemini exploded")

        with patch.dict(os.environ, env):
            with patch('sys.argv', ["src/agent.py", "--pr-url", pr_url]):
                 runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_get_details.assert_called_once_with(pr_url, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_gemini_review.assert_called_once_with(mock_get_details.return_value, env["GEMINI_API_KEY"])
        mock_post_comment.assert_not_called()
        mock_print.assert_any_call("\n--- Error During Gemini Review Process ---")
        mock_print.assert_any_call("RuntimeError - Gemini exploded")

    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True)
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_pr_url_gemini_review_returns_error_string(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print):
        env = {"GITHUB_PERSONAL_ACCESS_TOKEN": "gh_token", "GEMINI_API_KEY": "gem_key"}
        pr_url = "http://github.com/test/repo/pull/1"
        mock_get_details.return_value = {"title": "T", "body": "B", "diff": "D"}
        mock_gemini_review.return_value = "Error with Gemini API: Some problem"

        with patch.dict(os.environ, env):
            with patch('sys.argv', ["src/agent.py", "--pr-url", pr_url]):
                 runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_get_details.assert_called_once_with(pr_url, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_gemini_review.assert_called_once_with(mock_get_details.return_value, env["GEMINI_API_KEY"])
        mock_post_comment.assert_not_called()
        mock_print.assert_any_call("\n--- Gemini PR Review ---") # Verifies the review_text is printed
        mock_print.assert_any_call("Error with Gemini API: Some problem")
        mock_print.assert_any_call("\nSkipping GitHub comment posting due to issues with Gemini review generation or empty diff.")

    @patch('builtins.print')
    @patch.dict(os.environ, {}, clear=True)
    @patch('agent.run_agent')
    @patch('agent.post_pr_comment')
    @patch('agent.get_gemini_review')
    @patch('agent.get_pr_details')
    def test_main_flow_pr_url_post_comment_fails(self, mock_get_details, mock_gemini_review, mock_post_comment, mock_run_agent, mock_os_environ_dict, mock_print):
        env = {"GITHUB_PERSONAL_ACCESS_TOKEN": "gh_token", "GEMINI_API_KEY": "gem_key"}
        pr_url = "http://github.com/test/repo/pull/1"
        mock_get_details.return_value = {"title": "T", "body": "B", "diff": "D"}
        mock_gemini_review.return_value = "This is a great PR!"
        mock_post_comment.return_value = False # Simulate post_pr_comment failing

        with patch.dict(os.environ, env):
            with patch('sys.argv', ["src/agent.py", "--pr-url", pr_url]):
                 runpy.run_module("agent", run_name="__main__", alter_sys=True)

        mock_get_details.assert_called_once_with(pr_url, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_gemini_review.assert_called_once_with(mock_get_details.return_value, env["GEMINI_API_KEY"])
        mock_post_comment.assert_called_once_with(pr_url, mock_gemini_review.return_value, env["GITHUB_PERSONAL_ACCESS_TOKEN"])
        mock_print.assert_any_call("Failed to post review comment to the PR.")


# Renaming existing TestAgent to TestRunAgentMCP for clarity, as it tests the run_agent MCP path
class TestRunAgentMCP(unittest.TestCase):

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen") # This is subprocess.Popen
    def test_run_agent_success(self, mock_subprocess_popen): # Renamed argument for clarity
        # Mock the Popen process object and its communicate method
        mock_process = MagicMock() # This represents the Popen instance
        mock_process.returncode = 0

        # Expected MCP response payload for a successful 'get_me' tool call
        mcp_response_payload = {
            "tool_result": {
                "tool_name": "get_me",
                "result": {
                    "login": "testuser",
                    "name": "Test User",
                    "id": 12345
                }
            }
        }
        # MCP server typically outputs newline-delimited JSON
        stdout_data = json.dumps(mcp_response_payload) + "\n"
        stderr_data = "" # No error output expected on stderr for success

        # Configure the mock_process.communicate() method to return the expected stdout and stderr
        mock_process.communicate.return_value = (stdout_data, stderr_data)

        # Configure mock_popen (the Popen class) to return our mock_process instance when called
        mock_subprocess_popen.return_value = mock_process

        # Run the agent function
        result = agent.run_agent()

        # Assert the agent's output
        self.assertEqual(result, "Hello, testuser! Your name is Test User (via MCP).")

        # Verify that subprocess.Popen was called correctly
        expected_mcp_command = [
            "docker", "run", "-i", "--rm",
            "-e", "GITHUB_PERSONAL_ACCESS_TOKEN=test_token", # Token from patched os.environ
            "ghcr.io/github/github-mcp-server"
        ]
        mock_subprocess_popen.assert_called_once() # Check Popen was called
        popen_call_args, popen_call_kwargs = mock_subprocess_popen.call_args
        self.assertEqual(popen_call_args[0], expected_mcp_command) # Check the command argument
        self.assertTrue(popen_call_kwargs.get("text")) # Check a keyword argument like 'text=True'

        # Verify the input sent to the MCP server process via communicate()
        expected_input_payload = {
            "mcp_version": "0.1.0",
            "tool_invocation": {
                "tool_name": "get_me",
                "arguments": {}
            }
        }
        expected_input_json = json.dumps(expected_input_payload) + "\n"
        # Check that mock_process.communicate was called with the correct input and timeout
        mock_process.communicate.assert_called_once_with(input=expected_input_json, timeout=60)

    @patch.dict(os.environ, {}, clear=True) # Ensure a clean environment for this test
    def test_run_agent_missing_token(self):
        # Test the case where GITHUB_PERSONAL_ACCESS_TOKEN is not set
        with self.assertRaisesRegex(ValueError, "GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set."):
            agent.run_agent()

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_mcp_process_error(self, mock_subprocess_popen):
        # Test MCP server process failure (e.g., Docker command fails)
        mock_process = MagicMock()
        mock_process.returncode = 1 # Non-zero return code indicates an error
        # Simulate error message on stderr
        mock_process.communicate.return_value = ("", "Docker error: MCP server failed to start")
        mock_subprocess_popen.return_value = mock_process

        result = agent.run_agent()
        self.assertEqual(result, "MCP Server process error (return code 1): Docker error: MCP server failed to start")

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_mcp_tool_error_response(self, mock_subprocess_popen):
        # Test MCP server returning a structured error in its JSON response
        mock_process = MagicMock()
        mock_process.returncode = 0 # Process itself succeeded

        mcp_error_response_payload = {
            "error": { # MCP standard error structure
                "message": "Invalid token or insufficient permissions",
                "code": 401 # Example error code
            }
        }
        stdout_data = json.dumps(mcp_error_response_payload) + "\n"
        mock_process.communicate.return_value = (stdout_data, "") # No stderr error
        mock_subprocess_popen.return_value = mock_process

        result = agent.run_agent()
        expected_error_details_json = json.dumps(mcp_error_response_payload['error'])[:500]
        self.assertEqual(result, f"Error from MCP server: Invalid token or insufficient permissions. Details: {expected_error_details_json}")

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_mcp_timeout(self, mock_subprocess_popen):
        # Test timeout during communication with MCP server
        mock_process = MagicMock()
        # Configure communicate method to raise TimeoutExpired
        mock_process.communicate.side_effect = subprocess.TimeoutExpired(cmd="docker run ...", timeout=60)
        mock_subprocess_popen.return_value = mock_process

        result = agent.run_agent()
        # The agent's error handler for TimeoutExpired uses stderr_data if available,
        # which is initialized to "" in the agent and might not be updated if communicate fails early.
        self.assertIn("MCP Server process timed out after 60s", result)
        self.assertIn("Stderr: N/A", result) # Based on current agent error handling for timeout

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_json_decode_error(self, mock_subprocess_popen):
        # Test MCP server returning non-JSON output
        mock_process = MagicMock()
        mock_process.returncode = 0
        stdout_data = "This is not valid JSON output\n" # Malformed or non-JSON string
        mock_process.communicate.return_value = (stdout_data, "")
        mock_subprocess_popen.return_value = mock_process

        result = agent.run_agent()
        # Check for the specific error message from the agent's JSON parsing failure path
        self.assertIn("Failed to find or parse a JSON response from MCP server.", result)
        self.assertIn("Raw stdout: This is not valid JSON output", result)

if __name__ == "__main__":
    unittest.main()
