# My Agent Project

This project is a sample agent created with Python, using `uv` for package management and `mypy` for type checking.

## Setup

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

## Running the Agent

To run the sample agent:

```bash
python src/agent.py
```

You should see the output: `Hello, World! This is your agent speaking.`

## Type Checking

To check types using mypy:

```bash
mypy src/agent.py
```
Or to check all files in the src directory:
```bash
mypy src
```

The command should report `Success: no issues found` if everything is correctly typed.

This project is a demonstration of a simple agent.
