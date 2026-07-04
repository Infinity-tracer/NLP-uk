# Centralized Environment Configuration (Task 21)

## Overview

Centralized configuration is implemented in `centralized_config.py` with environment-specific JSON configs and optional AWS Secrets Manager overrides.

## Files

- Loader: `centralized_config.py`
- Environment configs:
  - `config/runtime/dev.json`
  - `config/runtime/staging.json`
  - `config/runtime/prod.json`
- Tests: `test_centralized_config.py`

## Capabilities

1. **Environment support**
   - Resolves `dev/staging/prod` using `APP_ENV` or explicit argument.

2. **No hardcoded credentials**
   - Uses AWS SDK credential chain (environment variables/profile/IAM role).
   - Config only stores `credentials_mode` metadata, not secrets.

3. **Secrets Manager integration**
   - Reads secret names from config (`secrets.secret_names`).
   - Merges secret payload values into effective runtime config.
   - Enabled explicitly via `load_runtime_config(..., load_secrets=True)` or `CONFIG_LOAD_SECRETS=1`.

4. **Config schema validation**
   - Validates required top-level keys and object types.

5. **Model parameters**
   - Supports thresholds, weights, chunking parameters.
   - Supports env override: `FINAL_CONFIDENCE_THRESHOLD`.

6. **Feature flags**
   - `enable_tier3`
   - `enable_semantic_fallback`
   - `enable_validation_layer`
   - `enable_prompt_ab_testing`
   - Access via `is_feature_enabled(...)`.

## Usage

```python
from centralized_config import load_runtime_config, get_model_parameter, is_feature_enabled

cfg = load_runtime_config(environment="staging")
threshold = get_model_parameter(cfg, "confidence_threshold", 0.85)
tier3_enabled = is_feature_enabled(cfg, "enable_tier3", default=False)
```

## Security

- Use AWS Secrets Manager for sensitive values.
- Use `redact_effective_config(...)` when printing or exporting configs.
