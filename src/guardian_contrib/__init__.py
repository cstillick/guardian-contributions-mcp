"""Guardian Contributions service.

Translates the manual Oklahoma Campaign-Finance Combined Reports workflow
(Pre-Primary + Continuing) into a reusable backend API + MCP front-end.

Source of truth for the business rules: Continuing_Reports_Workflow_Instructions.md
(the 14 Hard Rules). Each rule is enforced as a service invariant; see
guardian_contrib.compute and the test suite.
"""

__version__ = "0.1.0"
