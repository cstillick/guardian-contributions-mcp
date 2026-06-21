"""Ingestion workers — codify Section 4 of the workflow.

Network-touching code (Guardian fetches) lives here and ONLY here; the API and
MCP layers read from the normalized store and never hit Guardian on the request
path.
"""
