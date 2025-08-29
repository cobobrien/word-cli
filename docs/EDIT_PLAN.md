# Edit Plan Tool

This document defines a simple JSON schema for batch editing and how it maps to the new `apply_edit_plan` tool.

## Overview

`apply_edit_plan` lets the agent (or user) perform multiple edits deterministically. It supports preview mode where no changes are written and a concise summary is returned.

## Input Schema

Top-level keys:
- `plan`: object with an `operations` array
- `preview` (boolean, default: true): run without modifying the document
- `stop_on_error` (boolean, default: true): stop on the first failing operation when not in preview

Operation objects in `operations` must have a `type` and operation-specific fields. Supported types:

1) `edit_paragraph`
- `index` (1-based integer)
- `new_text` (string)

2) `insert_text`
- `position` (1-based integer; insert after this paragraph index)
- `text` (string)

3) `delete_paragraph`
- `index` (1-based integer)

4) `replace_all`
- `find` (string)
- `replace` (string)
- `case_sensitive` (boolean, optional, default false)

## Examples

Preview a change plan:
```json
{
  "plan": {
    "operations": [
      {"type": "edit_paragraph", "index": 2, "new_text": "Updated content."},
      {"type": "insert_text", "position": 2, "text": "New paragraph after 2."},
      {"type": "replace_all", "find": "foo", "replace": "bar"}
    ]
  },
  "preview": true
}
```

Apply a change plan and stop on first error:
```json
{
  "plan": {
    "operations": [
      {"type": "delete_paragraph", "index": 5},
      {"type": "edit_paragraph", "index": 7, "new_text": "Appendix updated."}
    ]
  },
  "preview": false,
  "stop_on_error": true
}
```

## Result Shape

The tool returns a `ToolExecutionResult` with:
- `success`: boolean
- `content`: human-readable summary
- `document_modified`: true if changes were applied
- `changes`: array of `DocumentChange` records (when applied)
- `data`: includes `preview`, `operations`, and `applied_changes` counts

## Rationale

- Keeps LLM operations constrained to a safe, typed subset.
- Allows preview/confirmation loops before committing changes.
- Composes well with transaction/validation layers and version control.

