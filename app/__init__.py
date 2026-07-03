"""FastAPI application layer for the M.A.R.I.A. Micro-Engine.

Exposes an OpenAI-compatible API (same endpoints and parameters), so any
application that talks to the OpenAI API can point at the Micro-Engine as a
drop-in replacement. Thin shell: all character logic lives in `engine/`.
"""
