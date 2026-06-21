"""Computation layer — the 14 Hard Rules as enforced invariants.

Pure functions over normalized records (testable without a DB) plus thin
session-bound wrappers. The API/MCP never re-implement these rules; they call here.
"""
