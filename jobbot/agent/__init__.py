"""The agent scoring loop — the project's core learning piece.

`loop.run_scoring_loop` drives a Claude Agent SDK perceive -> decide -> act loop
over unscored jobs, using the custom tools in `tools.py`.
"""
