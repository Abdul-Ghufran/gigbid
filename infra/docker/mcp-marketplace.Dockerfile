FROM gigbid-python-base:latest
ENV MCP_HTTP=1
EXPOSE 8091
CMD ["python", "-m", "mcp_servers.marketplace.server", "--transport", "http", "--port", "8091"]
