# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY src/ /app/src/

# GitHub MCP Server setup
# Download and run the MCP server
# This requires Docker to be available in the environment where this Dockerfile is built.
# For now, we'll assume the MCP server is running separately or accessible via network.
# We will need to provide the GITHUB_PERSONAL_ACCESS_TOKEN as an environment variable when running the container.

# Make port 80 available to the world outside this container (if the agent needs to expose an HTTP server)
# EXPOSE 80

# Define environment variable
ENV PYTHONUNBUFFERED 1
ENV GITHUB_PERSONAL_ACCESS_TOKEN ""

# Run agent.py when the container launches
CMD ["python", "src/agent.py"]
