import os
import json
import subprocess
import argparse
import requests # Added for GitHub API calls
import google.generativeai as genai # Added for Gemini API calls

def get_gemini_review(pr_details: dict, api_key: str) -> str:
    """
    Generates a PR review using the Gemini API.
    """
    # Special condition for testing without actual Gemini API calls
    if api_key == "SIMULATE_SUCCESSFUL_GEMINI_REVIEW":
        print("SIMULATING successful Gemini review for testing purposes.")
        return "This is a simulated successful Gemini review. Looks good!"

    try:
        genai.configure(api_key=api_key)
        # Using gemini-1.5-pro-latest as a robust and generally available model.
        # Alternative could be 'gemini-pro' if specific versioning is an issue.
        model = genai.GenerativeModel('gemini-1.5-pro-latest')

        title = pr_details.get("title", "N/A")
        body = pr_details.get("body", "")
        diff = pr_details.get("diff", "")

        if not diff:
            return "Skipping review as the PR diff is empty or not provided."

        prompt = f"""Please act as a code reviewer. Review the following pull request based on its title, body, and especially the diff. Provide feedback on potential bugs, areas for improvement, style issues, and overall code quality. Be concise and constructive.

PR Title: {title}

PR Body:
{body}

PR Diff:
```diff
{diff}
```
"""
        # It's good practice to ensure the prompt isn't excessively long, though Pro models have large context windows.
        # For now, we assume the diff is reasonably sized.
        # A production system might need token counting and truncation strategies for very large diffs.

        response = model.generate_content(prompt)

        if not response.text: # Check if response.text is None or empty
            # Attempt to access parts if available and provide more details
            if not response.parts:
                 return "Gemini API returned an empty response with no parts."
            # If there are parts, but .text is still empty, it's an unusual case.
            # Log the parts or their types for debugging.
            # For now, a generic message:
            return f"Gemini API returned a response, but the primary text content was empty. Parts available: {len(response.parts)}"


        return response.text

    except Exception as e:
        # Catching a broad exception, but specific errors from genai SDK could be handled too.
        # For example, google.api_core.exceptions.PermissionDenied for bad API key (often caught by genai.configure or first call)
        # or google.api_core.exceptions.ResourceExhausted for quota issues.
        # The SDK might wrap these in its own exception types as well.
        # A common one if the API key is invalid might be genai.types.generation_types.BlockedPromptException or similar if content filtering is triggered
        # or a general configuration error.

        # Let's try to give a more specific message for API key issues if possible by checking common exception types from the SDK
        # This is a guess; actual exception types may vary based on SDK version and error cause.
        if "API_KEY_INVALID" in str(e) or "API key not valid" in str(e) or isinstance(e, genai.types.generation_types.BlockedPromptException): # Heuristic check
            return f"Error with Gemini API: Potentially an invalid API key or a problem with the prompt/content. Details: {e}"
        # Add more specific genai exception checks here if known
        # For instance, if 'PermissionDenied' or 'Unauthenticated' is in the error string and relates to the API key
        if "PermissionDenied" in str(e) or "Unauthenticated" in str(e):
            return f"Error with Gemini API: Permission denied or unauthenticated. This is likely an issue with the API key. Details: {e}"

        return f"Error during Gemini API call: {type(e).__name__} - {e}"

def post_pr_comment(pr_url: str, comment_body: str, token: str) -> bool:
    """
    Posts a comment to the specified GitHub Pull Request.
    """
    try:
        # Parse PR URL (similar to get_pr_details)
        parts = pr_url.split("/")
        if not (
            pr_url.startswith("https://") and
            len(parts) >= 7 and
            "." in parts[2] and # Basic check for a hostname
            parts[5] == "pull" and
            parts[6].isdigit()
        ):
            raise ValueError(f"Invalid PR URL for posting comment: '{pr_url}'")

        owner = parts[3]
        repo = parts[4]
        # GitHub API uses issue number for PR comments, which is the same as pull_number
        issue_number = parts[6]

        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        payload = json.dumps({"body": comment_body})

        response = requests.post(api_url, headers=headers, data=payload, timeout=30)

        if response.status_code == 201: # 201 Created is success for this POST request
            print(f"Successfully posted comment to {pr_url}. Response: {response.status_code}")
            return True
        else:
            # Attempt to get more details from response for error logging
            try:
                error_details = response.json() # GitHub usually returns JSON errors
            except json.JSONDecodeError:
                error_details = response.text[:200] # Fallback to raw text if not JSON
            print(f"Failed to post comment to {pr_url}. Status: {response.status_code}, Details: {error_details}")
            response.raise_for_status() # This will raise an HTTPError for 4xx/5xx
            return False # Should not be reached if raise_for_status() works

    except requests.exceptions.HTTPError as e:
        # Specific error message for HTTP errors
        print(f"GitHub API request failed to post comment (HTTP {e.response.status_code}): {e.response.text[:500]}")
        if e.response.status_code == 401:
            print(" (Check your GITHUB_PERSONAL_ACCESS_TOKEN for necessary permissions)")
        elif e.response.status_code == 403:
            print(" (Forbidden - check token permissions, PR might be locked, or you might not have write access)")
        elif e.response.status_code == 404:
            print(" (Not Found - check owner, repo, or PR number; or PR might not be found)")
        # Do not re-raise here, allow main to handle the False return or a custom exception if preferred
        return False
    except requests.exceptions.RequestException as e:
        # For network errors, timeouts, etc.
        print(f"GitHub API request failed to post comment due to a network issue: {e}")
        return False
    except ValueError as e: # Catch our own ValueError from URL parsing
        print(f"Error preparing to post comment: {e}")
        return False
    except Exception as e:
        # Catch any other unexpected errors during the process
        print(f"An unexpected error occurred while posting comment: {type(e).__name__} - {e}")
        return False

def get_pr_details(pr_url: str, token: str) -> dict:
    """
    Fetches PR details (title, body, diff) from GitHub API.
    """
    # Special condition for testing without actual GitHub API calls
    if token == "SIMULATE_SUCCESSFUL_PR_FETCH":
        print("SIMULATING successful PR fetch for testing purposes.")
        return {
            "title": "Test PR Title",
            "body": "This is the body of the test PR.",
            "diff": """diff --git a/test.py b/test.py
index 0000001..0000002 100644
--- a/test.py
+++ b/test.py

-old_line
+new_line
+another_new_line
"""
        }

    try:
        # Parse PR URL
        # Example: https://github.com/owner/repo/pull/123
        # After split: ['https:', '', 'github.com', 'owner', 'repo', 'pull', '123']
        parts = pr_url.split("/")
        # Basic validation:
        # Should have at least 7 parts (https: + empty + host + owner + repo + "pull" + number)
        # parts[2] should be a hostname (e.g. github.com)
        # parts[5] should be "pull"
        # parts[6] should be a digit (the PR number)
        if not (
            pr_url.startswith("https://") and
            len(parts) >= 7 and
            "." in parts[2] and # Basic check for a hostname
            parts[5] == "pull" and
            parts[6].isdigit()
        ):
            # Try to provide more context if parsing fails
            if not pr_url.startswith("https://") or "github.com" not in parts[2]: # check for github.com in host part
                 raise ValueError(f"Invalid PR URL: Does not seem to be a valid HTTPS GitHub URL. URL: '{pr_url}'")
            if len(parts) < 7 or parts[5] != "pull" or not parts[6].isdigit():
                 raise ValueError(f"Invalid PR URL structure: Expected 'https://<host>/owner/repo/pull/number'. URL: '{pr_url}'")

            # Default error for general parsing issues
            raise ValueError(f"Invalid PR URL format. URL: '{pr_url}'")

        owner = parts[3]
        repo = parts[4]
        pull_number = parts[6]

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json" # For PR details
        }

        # Fetch PR details (title, body)
        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        pr_data = response.json()
        title = pr_data.get("title", "N/A")
        body = pr_data.get("body", "") # Body can be None, so default to empty string

        # Fetch PR diff
        headers["Accept"] = "application/vnd.github.v3.diff" # For PR diff
        diff_response = requests.get(api_url, headers=headers, timeout=30)
        diff_response.raise_for_status()
        diff_content = diff_response.text

        return {
            "title": title,
            "body": body if body is not None else "", # Ensure body is not None
            "diff": diff_content
        }
    except requests.exceptions.HTTPError as e:
        # More specific error message including status code and response if available
        error_message = f"GitHub API request failed (HTTP {e.response.status_code}): {e.response.text[:500]}"
        # Check for common issues like bad credentials or rate limiting
        if e.response.status_code == 401:
            error_message += " (Check your GITHUB_PERSONAL_ACCESS_TOKEN)"
        elif e.response.status_code == 403:
            error_message += " (Forbidden - check token permissions or rate limits)"
        elif e.response.status_code == 404:
            error_message += " (Not Found - check owner, repo, or PR number)"
        raise ValueError(error_message) from e
    except requests.exceptions.RequestException as e:
        # For network errors, timeouts, etc.
        raise ValueError(f"GitHub API request failed due to a network issue: {e}") from e
    except ValueError as e: # Catch our own ValueError from URL parsing
        raise # Re-raise it
    except Exception as e:
        # Catch any other unexpected errors during the process
        raise RuntimeError(f"An unexpected error occurred while fetching PR details: {e}") from e

def run_agent() -> str:
    """
    An agent that interacts with the GitHub MCP server via stdio to get user details.
    """
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set.")

    # Command to run the MCP server in a Docker container
    # The GitHub token is passed as an environment variable to the container
    mcp_command = [
        "docker", "run", "-i", "--rm", # -i for interactive (to use stdin), --rm to clean up
        "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={token}",
        "ghcr.io/github/github-mcp-server"
    ]

    # MCP request payload for the 'get_me' tool
    # Following a more standard MCP structure for requests
    request_payload = {
        "mcp_version": "0.1.0",
        "tool_invocation": {
             "tool_name": "get_me",
             "arguments": {}
        }
    }
    # MCP messages are typically newline-delimited JSON
    request_json = json.dumps(request_payload) + "\n"

    stdout_data = "" # Initialize to ensure it's defined for error reporting
    stderr_data = "" # Initialize to ensure it's defined for error reporting

    try:
        # Start the MCP server process and send the request to its stdin
        # Read stdout and stderr until the process terminates
        process = subprocess.Popen(
            mcp_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True # Work with text (UTF-8) streams
        )

        # Communicate sends input, waits for process to terminate, and returns output/error
        stdout_data, stderr_data = process.communicate(input=request_json, timeout=60) # Increased timeout to 60s

        if process.returncode != 0:
            # MCP server process exited with an error
            error_message = stderr_data.strip() if stderr_data.strip() else "Unknown error from MCP server process."
            # Sometimes, error details might be on stdout if stderr is empty and process failed
            if not stderr_data.strip() and stdout_data.strip():
                error_message = stdout_data.strip()
            return f"MCP Server process error (return code {process.returncode}): {error_message[:1000]}" # Limit error message length

        if not stdout_data.strip():
            # No output received on stdout, which is unexpected for a successful call
            error_info = stderr_data.strip() if stderr_data.strip() else "No error message on stderr."
            return f"No response from MCP server on stdout. Stderr: {error_info[:1000]}"

        # MCP servers can send multiple JSON objects, newline-delimited.
        # We need to parse the relevant JSON object that contains the tool result.
        # It's often the last valid JSON object, or one that matches the "tool_result" structure.
        parsed_response = None
        last_json_decode_error = None

        # Iterate through lines to find a valid MCP JSON response
        # Prefer responses that contain 'tool_result' or 'error' keys.
        candidate_lines = stdout_data.strip().splitlines()
        for line in reversed(candidate_lines): # Check from last line first
            if not line.strip():
                continue
            try:
                current_json = json.loads(line)
                if "tool_result" in current_json or "error" in current_json:
                    parsed_response = current_json
                    break
                if parsed_response is None: # If no ideal MCP response yet, take the first valid JSON from end
                    parsed_response = current_json
            except json.JSONDecodeError as e:
                if last_json_decode_error is None : # Store first decode error encountered from end
                    last_json_decode_error = e

        if parsed_response is None:
            error_context = f"Raw stdout: {stdout_data.strip()[:500]}"
            if last_json_decode_error:
                 return f"Failed to find or parse a JSON response from MCP server. Last decode error: {last_json_decode_error}. {error_context}"
            return f"No valid JSON response found in MCP server stdout. {error_context}"

        response_data = parsed_response

        # Check for MCP-level errors in the response
        if "error" in response_data:
            error_details = response_data.get("error", {})
            return f"Error from MCP server: {error_details.get('message', 'Unknown MCP error')}. Details: {json.dumps(error_details)[:500]}"

        # Expecting result in a "tool_result" field as per common MCP patterns
        tool_result_wrapper = response_data.get("tool_result")
        if not tool_result_wrapper:
            if "login" in response_data and "id" in response_data:
                 actual_result = response_data
            else:
                return f"Unexpected MCP response format. Missing 'tool_result' and response doesn't look like user data. Response: {json.dumps(response_data)[:500]}"
        else:
            actual_result = tool_result_wrapper.get("result")
            if actual_result is None:
                 return f"MCP tool result is missing or null within 'tool_result'. Full 'tool_result' content: {json.dumps(tool_result_wrapper)[:500]}"

        user_login = actual_result.get("login", "N/A")
        user_name = actual_result.get("name", "N/A")

        return f"Hello, {user_login}! Your name is {user_name} (via MCP)."

    except subprocess.TimeoutExpired:
        stderr_content = stderr_data.strip()[:500] if stderr_data else 'N/A'
        return f"MCP Server process timed out after 60s. This might happen if the Docker image needs to be pulled or the server is slow to start/process. Stderr: {stderr_content}"
    except subprocess.SubprocessError as e:
        return f"Failed to run/communicate with MCP server process: {e}"
    except json.JSONDecodeError as e:
        raw_output_for_error = stdout_data.strip()[:500] if stdout_data else "No stdout data captured."
        return f"Error: Could not decode JSON response from MCP server (unexpectedly). Error: {e}. Received: '{raw_output_for_error}'"
    except Exception as e:
        return f"An unexpected error occurred: {type(e).__name__} - {e}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent to interact with GitHub MCP server or process a PR URL.")
    parser.add_argument("--pr-url", type=str, help="GitHub Pull Request URL")
    args = parser.parse_args()

    if args.pr_url:
        print(f"Processing PR URL: {args.pr_url}")
        token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        if not token:
            print("\n--- Configuration Error ---")
            print("GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set. Cannot fetch PR details.")
        else:
            try:
                print("Fetching PR details...")
                pr_details = get_pr_details(args.pr_url, token)
                print("\n--- PR Details ---")
                print(f"Title: {pr_details['title']}")
                body_snippet = pr_details['body'][:200] + "..." if pr_details['body'] else "(empty)"
                print(f"Body: {body_snippet}")
                diff_snippet = pr_details['diff'][:500] + "..." if pr_details['diff'] else "(empty)"
                print(f"Diff: \n{diff_snippet}")

                # Now, try to get Gemini review
                gemini_api_key = os.environ.get("GEMINI_API_KEY")
                if not gemini_api_key:
                    print("\n--- Gemini Configuration Error ---")
                    print("GEMINI_API_KEY environment variable not set. Cannot get PR review.")
                else:
                    print("\n--- Getting Gemini Review ---")
                    try:
                        review_text = get_gemini_review(pr_details, gemini_api_key)
                        print("\n--- Gemini PR Review ---")
                        print(review_text)

                        # Check if review was successful before attempting to post
                        if not review_text.startswith("Error with Gemini API:") and \
                           not review_text.startswith("Gemini API returned an empty response") and \
                           not review_text == "Skipping review as the PR diff is empty or not provided.":
                            print("\n--- Posting Review to GitHub PR ---")
                            # The GITHUB_PERSONAL_ACCESS_TOKEN used for get_pr_details is in 'token' variable
                            if post_pr_comment(args.pr_url, review_text, token):
                                print("Successfully posted review comment to the PR.")
                            else:
                                print("Failed to post review comment to the PR.")
                        else:
                            print("\nSkipping GitHub comment posting due to issues with Gemini review generation or empty diff.")

                    except Exception as e: # Catch errors from get_gemini_review itself
                        print(f"\n--- Error During Gemini Review Process ---")
                        print(f"{type(e).__name__} - {e}")

            except (ValueError, RuntimeError) as e:
                print(f"\n--- Error Fetching PR Details ---")
                print(f"{e}")
            except Exception as e:
                print(f"\n--- An Unexpected Error Occurred ---")
                print(f"{type(e).__name__} - {e}")
    else:
        print("No PR URL provided. Attempting to run default agent logic...")
        print("Please ensure Docker is running and you have set the GITHUB_PERSONAL_ACCESS_TOKEN environment variable.")
        print("The agent will attempt to run 'ghcr.io/github/github-mcp-server' via Docker.")
        print("This may take a moment if the Docker image needs to be pulled (timeout is 60s).")

        try:
            message = run_agent()
            print("\n--- Agent Result ---")
            print(message)
        except ValueError as e:
            print(f"\n--- Configuration Error ---")
            print(f"{e}")
        except Exception as e:
            print(f"\n--- Agent Run Failed ---")
            print(f"{type(e).__name__} - {e}")
