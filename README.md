# Prebid Agent Toolkit

This project is a sample agent created with Python. It can be run locally or using Docker, with Docker being the primary method for interacting with the GitHub MCP Server.

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

*   **Docker**: Ensure Docker is installed and the Docker daemon is running.
*   **GitHub Personal Access Token (PAT)**: You'll need a GitHub PAT. You can [create one here](https://github.com/settings/personal-access-tokens/new). The token will need permissions relevant to the tools you intend to use via the MCP server (e.g., `read:user` for the `get_me` tool).

### Environment Variable

The agent requires your GitHub PAT to be set as an environment variable for the Docker container that runs the agent:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="your_github_pat_here"
```
Make sure this variable is exported in the shell session from which you run the `docker run` command.

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
    prebid-agent-mcp
```

**Explanation of the command:**
*   `--rm`: Automatically removes the container when it exits.
*   `-v /var/run/docker.sock:/var/run/docker.sock`: This mounts the Docker socket from your host into the container. It's **required** because the agent script itself executes `docker run` to start the `ghcr.io/github/github-mcp-server` Docker image.
*   `-e GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN`: This passes your GitHub PAT into the agent's container. The agent script then uses this token to authenticate when it, in turn, starts the MCP server container.
*   `prebid-agent-mcp`: The name of the image you built.

The agent will then start, invoke the GitHub MCP server (by running its Docker image), call the `get_me` tool via the MCP server, and print a greeting with your GitHub login and name.

## Running the Agent Locally (Python directly)

You can also run the agent directly using Python if you have set up your environment as described in the "Setup" section.

```bash
python src/agent.py
```

**Note**: When run this way, the `src/agent.py` script will attempt to use `docker` commands to launch the MCP server (`ghcr.io/github/github-mcp-server`). This means:
1.  Docker must be installed and the Docker daemon running.
2.  The `GITHUB_PERSONAL_ACCESS_TOKEN` environment variable must be set in your current shell session:
    ```bash
    export GITHUB_PERSONAL_ACCESS_TOKEN="your_github_pat_here"
    ```
If Docker is not available or the MCP server container cannot be launched, the agent will fail. The Dockerized setup described in the previous section is the primary and more robust method for running the agent with MCP integration, as it ensures the agent's execution environment is correctly configured.

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
