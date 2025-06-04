import os
import unittest
from unittest.mock import patch, MagicMock
import json
import subprocess # Required for subprocess.TimeoutExpired

# Add src to path to allow direct import of agent
# This allows running tests from the project root (e.g., python -m unittest discover tests)
# or from the tests directory (e.g., python test_agent.py)
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# The module to be tested
import agent

class TestAgent(unittest.TestCase):

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_success(self, mock_popen):
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
        mock_popen.return_value = mock_process

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
        mock_popen.assert_called_once() # Check Popen was called
        popen_call_args, popen_call_kwargs = mock_popen.call_args
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
    def test_run_agent_mcp_process_error(self, mock_popen):
        # Test MCP server process failure (e.g., Docker command fails)
        mock_process = MagicMock()
        mock_process.returncode = 1 # Non-zero return code indicates an error
        # Simulate error message on stderr
        mock_process.communicate.return_value = ("", "Docker error: MCP server failed to start")
        mock_popen.return_value = mock_process

        result = agent.run_agent()
        self.assertEqual(result, "MCP Server process error (return code 1): Docker error: MCP server failed to start")

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_mcp_tool_error_response(self, mock_popen):
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
        mock_popen.return_value = mock_process

        result = agent.run_agent()
        expected_error_details_json = json.dumps(mcp_error_response_payload['error'])[:500]
        self.assertEqual(result, f"Error from MCP server: Invalid token or insufficient permissions. Details: {expected_error_details_json}")

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_mcp_timeout(self, mock_popen):
        # Test timeout during communication with MCP server
        mock_process = MagicMock()
        # Configure communicate method to raise TimeoutExpired
        mock_process.communicate.side_effect = subprocess.TimeoutExpired(cmd="docker run ...", timeout=60)
        mock_popen.return_value = mock_process

        result = agent.run_agent()
        # The agent's error handler for TimeoutExpired uses stderr_data if available,
        # which is initialized to "" in the agent and might not be updated if communicate fails early.
        self.assertIn("MCP Server process timed out after 60s", result)
        self.assertIn("Stderr: N/A", result) # Based on current agent error handling for timeout

    @patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "test_token"})
    @patch("subprocess.Popen")
    def test_run_agent_json_decode_error(self, mock_popen):
        # Test MCP server returning non-JSON output
        mock_process = MagicMock()
        mock_process.returncode = 0
        stdout_data = "This is not valid JSON output\n" # Malformed or non-JSON string
        mock_process.communicate.return_value = (stdout_data, "")
        mock_popen.return_value = mock_process

        result = agent.run_agent()
        # Check for the specific error message from the agent's JSON parsing failure path
        self.assertIn("Failed to find or parse a JSON response from MCP server.", result)
        self.assertIn("Raw stdout: This is not valid JSON output", result)

if __name__ == "__main__":
    unittest.main()
