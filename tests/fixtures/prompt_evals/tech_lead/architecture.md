# Architecture — Config Validation API

## Summary

A single FastAPI app with one route. The route parses the YAML, runs it through a
schema validator, and returns the result.

## Components

- **`api.py`** — defines `POST /validate`. On success returns `{"valid": true}`.
  On failure returns `{"valid": false, "errors": list[str]}`.
- **`validator.py`** — `validate(config: dict) -> list[str]`. Returns a list of
  human-readable error messages (e.g. `"field 'timeout' must be an integer"`).
- **`models.py`** — Pydantic request/response models.

## Interfaces

```python
def validate(config: dict) -> list[str]: ...   # empty list == valid

class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = []                      # plain human-readable strings
```

## Data flow

1. Request body (YAML text) → `yaml.safe_load` → dict.
2. dict → `validate()` → list of error strings.
3. Wrap in `ValidateResponse` and return.

## Decisions

- Errors are returned as plain strings to keep the response simple.
- All problems are returned in a single list in one response.

## File changes overview

Create `api.py`, `validator.py`, `models.py`; no changes to existing files.
