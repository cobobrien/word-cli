# Word CLI – Improvements in this Change Set

This document explains what was changed, why it matters, and where to look in the code.

## Summary

- Fixed Pandoc AST defaults to use proper Pydantic field factories.
- Prevented Pandoc from being passed an empty `--reference-doc` and made it optional.
- Routed `--extract-media` to a temporary directory to avoid polluting user folders.
- Completed the Anthropic tool-result loop so the model can continue reasoning with tool outputs.
- Cleaned up unused/stdlib dependencies in `pyproject.toml`.

## Changes and Rationale

### 1) Correct Pydantic Defaults in PandocAST
- What: Replaced `dataclasses.field(default_factory=...)` with `pydantic.Field(default_factory=...)` for `blocks` and `meta`.
- Why: Using `dataclasses.field` inside a Pydantic `BaseModel` can create subtle default-sharing bugs. `Field(default_factory=...)` is the correct way to get per-instance default containers.
- Files:
  - `src/word_cli/core/document_model.py:16`

### 2) Safer Pandoc Invocation in AST→DOCX
- What: Only provide `--reference-doc` to Pandoc when a valid template path exists; otherwise omit the flag entirely.
- Why: Passing an empty string can cause Pandoc to error. Making it optional avoids spurious failures while keeping room for a user-configured template.
- Files:
  - `src/word_cli/converters/ast_to_docx.py:96`
  - `src/word_cli/converters/ast_to_docx.py:130`

### 3) Avoid Writing Media to the User’s Folder
- What: Changed `--extract-media` to use a `TemporaryDirectory()` instead of `<doc_dir>/media`.
- Why: Prevents unexpected files from appearing alongside user documents and keeps conversion side-effect free.
- Files:
  - `src/word_cli/converters/docx_to_ast.py:100`

### 4) Complete Anthropic Tool-Result Loop
- What: Updated the agent loop to iteratively:
  1. Stream a model response; collect `tool_use` blocks.
  2. Execute tools locally and display results immediately.
  3. Append a synthetic `user` message with `tool_result` blocks tied to the original `tool_use_id`.
  4. Make a follow-up model call with these tool results to allow the assistant to continue reasoning.
- Why: Without feeding `tool_result` back to the model, the assistant cannot incorporate tool outcomes into subsequent messages. This brings the loop in line with Anthropic’s tools flow.
- Files:
  - `src/word_cli/agent/agent_core.py:146`

### 5) Dependency Hygiene
- What: Removed unused dependencies: `pypandoc` (unused, we use `subprocess` directly) and `pathlib` (stdlib).
- Why: Keeps the install smaller and reduces maintenance surface.
- Files:
  - `pyproject.toml`

## Notes and Follow-ups

- Relationship injection and comments re-linking are still placeholders (by design) but now documented better by behavior. Future work can extend `_update_relationships()` and add real comment anchoring.
- Consider pinning the `anthropic` library to a version verified for the streaming tools API and expanding tests around the iterative tool loop.
- README currently overstates the number of tools and the maturity of some features; aligning docs with reality will reduce surprises for new users.

## Testing Hints

- Conversions:
  - Ensure Pandoc is on `PATH`.
  - Open a `.docx` with `word-cli open <file>` and confirm no `media/` folder appears next to the document.
- Agent:
  - With `ANTHROPIC_API_KEY` set, run `word-cli chat <file>` and request operations that trigger tools (e.g., “Find all instances of X” or “Edit paragraph 2…”). The assistant should execute tools, print results, and then continue its reasoning.

## Potential Compatibility Notes

- If a user previously depended on `pypandoc` being installed (though unused), poetry will no longer install it. All conversion logic continues to use Pandoc via `subprocess`.

