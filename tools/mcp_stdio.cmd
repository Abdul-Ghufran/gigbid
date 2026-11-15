@echo off
rem Start a GigBid MCP server over stdio from any working directory (used by MCP Inspector / Claude Desktop).
cd /d "%~dp0.."
call "%~dp0..\gb.cmd" %*
