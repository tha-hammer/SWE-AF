# PRD — Config Validation API

## Validated description

A small HTTP service that validates uploaded YAML config files and returns the
validation result. Single endpoint, JSON in / JSON out.

## Acceptance criteria

- **AC1**: `POST /validate` accepts a YAML body and returns `200 {"valid": true}`
  when the config parses and satisfies the schema.
- **AC2**: When validation fails, the response MUST include, for every problem, a
  machine-readable `code`, the offending `field` path, and the `line` and `column`
  where it occurred — so a client can render an inline annotation without parsing
  prose.
- **AC3**: Results are paginated: when there are more than 50 problems, the
  response returns the first 50 plus a `next_page` cursor.

## Out of scope

- Authentication, persistence, multi-file uploads.
