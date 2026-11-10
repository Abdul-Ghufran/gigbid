FROM gigbid-python-base:latest
ENV MCP_HTTP=1
EXPOSE 8092
CMD ["python", "-m", "mcp_servers.portfolio.server", "--transport", "http", "--port", "8092"]
