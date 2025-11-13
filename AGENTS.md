# Agent Workflow Guide

This repository is now configured for Cursor-first development. The `.cursor` directory captures all project-specific guardrails, Model Context Protocol (MCP) connections, and custom modes that agents should follow.

## Getting Started in Cursor
- Open the repository in Cursor; the workspace will automatically load `.cursor` settings.
- Review the project rules in `.cursor/rules` before starting any task to align with coding standards.
- Run `agent-setup.sh` if you need to bootstrap local tooling (linters, formatters, etc.).

## Project Rules
- `01-general.md` covers formatting, typing, docstring, testing, and Git expectations. Follow these rules for every contribution.
- `02-mcp.md` documents how and when to interact with MCP servers during development.

## MCP Servers
The `mcp.json` file configures the following servers:
- `memory`: Persists project knowledge. Use it to read existing context at task start and to store key findings or completions.
- `context7`: Provides up-to-date documentation lookups for libraries such as Pydantic, pytest, pandas, httpx/aiohttp, and FastAPI.

Each server lists commands that are always approved so you can call them without additional confirmation.

## Custom Cursor Modes
Cursor exposes two custom modes defined in `.cursor/modes.yaml`:
- `documentation-writer`: Full read/edit/command access optimized for producing high-quality documentation.
- `project-research`: Read-focused mode for deep codebase investigations with structured reporting expectations.

Switch modes in Cursor as tasks require to ensure the right guardrails and instructions are applied.

## Legacy Roo Configuration
The previous `.roo` configuration has been migrated to Cursor. Agents working outside Cursor should still respect the same rules and workflows outlined above.
