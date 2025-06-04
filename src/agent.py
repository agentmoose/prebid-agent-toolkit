import os
import json
import subprocess

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
    print("Attempting to run agent...")
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
