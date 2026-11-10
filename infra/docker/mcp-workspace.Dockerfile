FROM gigbid-python-base:latest
ENV MCP_HTTP=1
EXPOSE 8093
CMD ["python", "-m", "mcp_servers.workspace.server", "--transport", "http", "--port", "8093"]
