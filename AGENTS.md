# Project Agent Guidelines

## Multi-agent default

For implementation, debugging, and codebase analysis in this repository, use a multi-agent workflow by default:

1. Split work into independent tasks whenever possible.
2. Delegate each independent task to a focused subagent with clear scope and constraints.
3. Run independent subagents in parallel when there is no shared-state risk.
4. Integrate results centrally and resolve conflicts before finalizing.

## Delegation rules

- Prefer specialized subagents over doing all work in the main session.
- Keep each subagent prompt self-contained (goal, files, constraints, expected output).
- Use read-only exploration agents for discovery and architecture tracing.
- Use execution-oriented agents for implementation, fixes, and tests.
- Do not dispatch parallel agents for tightly coupled edits to the same files.

## Quality gates

- Require each subagent to summarize changes and risks.
- Run relevant tests/checks after integrating delegated changes.
- If a task is blocked, re-scope and re-dispatch with clearer context or a more capable agent.
