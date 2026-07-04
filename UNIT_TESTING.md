# Unit Testing (Task 16)

This repository uses `pytest` with `pytest-cov` for core-module unit testing.

## Scope

The unit suite targets:

- `preprocessing.py`
- `tier1_textract.py`
- `tier2_router.py`
- `track_a_snomed.py`
- `track_b_summarization.py`
- `track_b_validation.py`
- `lambda_confidence_aggregator.py`

## Run locally

```bash
pytest -q test_preprocessing.py test_tier1_textract_unit.py test_tier2_router.py test_track_a_snomed_unit.py test_track_b_summarization_unit.py test_track_b_validation.py test_lambda_confidence_aggregator.py
```

Coverage is configured in `pytest.ini` with `--cov-fail-under=80`.

## CI

GitHub Actions workflow: `.github/workflows/python-tests.yml`

- installs dependencies from `requirements.txt`
- runs pytest with coverage
- uploads `coverage.xml` artifact
