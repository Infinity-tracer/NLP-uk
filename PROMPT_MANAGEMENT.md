# Bedrock Prompt Management (Task 13)

This project now includes prompt version control for Track B Claude summarization calls.

## Scope

Prompt templates are versioned for:

1. `medical_summarization`
2. `role_based_actions`
3. `error_correction`

Template definitions and active versions are stored in:

- `prompt_management/prompt_registry.json`
- `prompt_management/prompt_change_log.json`

## Bedrock Prompt Management Integration

Runtime integration lives in `bedrock_prompt_management.py` and supports:

- Prompt draft create/update via `bedrock-agent` (`create_prompt`, `update_prompt`)
- Optional version snapshots via `create_prompt_version`
- Persistent mapping of Bedrock prompt identifiers/ARNs in local registry

Set these environment variables to control behavior:

- `PROMPT_MGMT_SYNC_ENABLED=true|false` (default: `false`)
- `PROMPT_MGMT_AUTO_SNAPSHOT=true|false` (default: `false`)
- `PROMPT_MANAGEMENT_DIR=<path>` (default: `prompt_management`)

## A/B Testing

A/B settings are in the `ab_tests` section of `prompt_registry.json`.

Assignment is deterministic by:

- template name
- document id
- role
- configured experiment salt

This gives reproducible routing while still allowing weighted split tests.

Use CLI:

```bash
python prompt_management_cli.py set-ab --template medical_summarization --enabled true --weights v1=0.7,v2=0.3 --rationale "Test stricter v2 prompts"
```

## Rollback

Rollback updates the active version and writes a change-log entry:

```bash
python prompt_management_cli.py rollback --template medical_summarization --version v1 --rationale "Revert due to lower factuality"
```

## Track B Output Traceability

Each Track B role output now includes:

- `prompt_tracking` (component-level version + selection metadata)
- `prompt_versions` (selected template versions)

This enables reproducibility/debugging for generated summaries.

## Change Rationale Workflow

Any version switch, rollback, or A/B config update should include a rationale.
Those rationales are persisted in `prompt_change_log.json` for auditability.
