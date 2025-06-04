# Prebid Agent Toolkit

This project is a sample agent created with Python. It can be run locally or using Docker, with Docker being the primary method for interacting with the GitHub MCP Server. It also includes a feature to review GitHub Pull Requests using AI.

## Configuration

Before running the agent, especially for the Pull Request Reviewer functionality or MCP server interaction, you need to configure the following environment variables:

*   **`GITHUB_PERSONAL_ACCESS_TOKEN`**:
    *   **Purpose**: Required for interacting with the GitHub API. This token is used to fetch pull request details, post comments on pull requests, and for the MCP server to interact with GitHub on your behalf.
    *   **Permissions**: Ensure the token has the necessary scopes. For public repositories, `public_repo` might be sufficient for PR reviews. For private repositories, `repo` scope is typically needed. For MCP server interactions (like the `get_me` tool), `read:user` might be required. The token should have at least read access to PR content and write access for posting comments if using the review feature.
    *   **Creation**: You can [create one here](https://github.com/settings/personal-access-tokens/new).

*   **`GEMINI_API_KEY`**:
    *   **Purpose**: Required for accessing Google's Gemini API to generate AI-powered code reviews for the Pull Request Reviewer feature.
    *   **Acquisition**: You'll need to obtain an API key from Google AI Studio or your Google Cloud project.

**Example (bash):**
```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="your_github_pat_here"
export GEMINI_API_KEY="your_gemini_api_key_here"
```

**Note on Docker:** If you are running the agent within a Docker container, these environment variables need to be passed into the Docker container (e.g., using the `-e` flag with `docker run`).

## Setup (For Local Development & Type Checking)

These steps are relevant if you want to run the agent directly using Python for development or perform type checking.

1.  **Clone the repository (if you haven't already):**
    ```bash
    # git clone <repository-url>
    # cd my_agent_project
    ```

2.  **Install uv (if you don't have it):**
    Follow the official installation instructions for uv: [https://github.com/astral-sh/uv#installation](https://github.com/astral-sh/uv#installation)
    Alternatively, if you have pipx:
    ```bash
    pipx install uv
    ```
    Or, if you have pip:
    ```bash
    pip install uv
    ```

3.  **Create and activate a virtual environment:**
    Navigate to the project root directory (`my_agent_project`) and run:
    ```bash
    uv venv
    source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
    ```

4.  **Install dependencies:**
    ```bash
    uv pip install -r requirements.txt
    ```

## Running the Agent with GitHub MCP Server (Docker)

This agent can leverage the GitHub MCP Server to interact with GitHub APIs. This setup uses Docker to run both the agent and the MCP server.

### Prerequisites

*   **Docker**: Ensure Docker is installed and the Docker daemon is running (if using Docker-based workflows).
*   **Environment Variables**: Ensure `GITHUB_PERSONAL_ACCESS_TOKEN` (and `GEMINI_API_KEY` if using the PR reviewer) are set as described in the "Configuration" section.

### Build the Agent Docker Image

Navigate to the project root directory and run:

```bash
docker build -t prebid-agent-mcp .
```

### Run the Agent

To run the agent and have it interact with the MCP server, execute the following command:

```bash
docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -e GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN \
    # -e GEMINI_API_KEY=$GEMINI_API_KEY # Uncomment if using PR reviewer via this Docker setup
    prebid-agent-mcp
```

**Explanation of the command:**
*   `--rm`: Automatically removes the container when it exits.
*   `-v /var/run/docker.sock:/var/run/docker.sock`: This mounts the Docker socket from your host into the container. It's **required** because the agent script itself executes `docker run` to start the `ghcr.io/github/github-mcp-server` Docker image.
*   The `-e` flags pass the necessary API keys into the agent's container. The agent script then uses these tokens.
*   `prebid-agent-mcp`: The name of the image you built.

The agent will then start. If run without arguments, it invokes the GitHub MCP server (by running its Docker image), calls the `get_me` tool via the MCP server, and prints a greeting. If run with `--pr-url`, it will perform the PR review.

## Running the Agent Locally (Python directly)

You can also run the agent directly using Python if you have set up your environment as described in the "Setup" section.

**For MCP Server Interaction (Default Behavior):**
```bash
python src/agent.py
```
**Note**: When run this way for MCP interaction, the `src/agent.py` script will attempt to use `docker` commands to launch the MCP server (`ghcr.io/github/github-mcp-server`). This means:
1.  Docker must be installed and the Docker daemon running.
2.  The `GITHUB_PERSONAL_ACCESS_TOKEN` environment variable must be set in your current shell session (see "Configuration").
If Docker is not available or the MCP server container cannot be launched, this mode will fail.

**For Pull Request Reviewer:**
```bash
python src/agent.py --pr-url "https://github.com/owner/repo/pull/PULL_NUMBER"
```
Ensure `GITHUB_PERSONAL_ACCESS_TOKEN` and `GEMINI_API_KEY` are set in your environment as per the "Configuration" section.

The Dockerized setup is the primary method for running the agent with MCP integration. The local Python execution is suitable for development, testing, and running the PR reviewer.

## Pull Request Reviewer

This agent includes a feature to automatically review GitHub Pull Requests using AI.

### Functionality
When provided with a GitHub Pull Request URL, the agent will:
1. Fetch the PR details (title, body, and diff) from the GitHub API.
2. Generate a code review using Google's Gemini model.
3. Post the generated review as a comment back to the original Pull Request on GitHub.

### How to Use
To trigger the PR review functionality, run the agent with the `--pr-url` command-line argument:

```bash
python src/agent.py --pr-url "https://github.com/owner/repo/pull/PULL_NUMBER"
```

This command should be run from an environment where the necessary environment variables are set (see "Configuration" section).

## Type Checking

To check types using mypy (ensure you've followed the "Setup" section first):

```bash
mypy src/agent.py
```
Or to check all files in the src directory:
```bash
mypy src
```

The command should report `Success: no issues found` if everything is correctly typed.
This project demonstrates an agent interacting with the GitHub MCP server.
