---
title: Seed Contract Explode Demo
task: Write Postgres seed script for exploded contract view
slug: seed-contract-explode-demo
effort: E3
phase: execute
progress: 0/16
mode: algorithm
started: 2026-06-26
updated: 2026-06-26
---

## Context

Write (DO NOT RUN) a Node.js seed script populating Postgres with a coherent
"Exploded Contract View" dataset based on REAL well-known vendor contracts
(AWS EDP, Salesforce MSA+order forms, Snowflake capacity commitment, Datadog,
Atlassian, Twilio, Equinix colocation). Saved to
`/home/maceo/Dev/cosmic-HR04-slice-contract-view/scripts/seed-contract-explode-demo.js`.

Reads `process.env.DATABASE_URL`, uses `pg`, idempotent transaction, deletes
prior rows by marker then re-inserts. org_id legacy_default
`05f7e9a8-7fd2-4372-89bb-c4901b6e5f42`, engagement_id `eng-orgchart-demo`.

Schema confirmed from migrations 064 (contracts/versions/clauses/obligations/
parties), 065 (contract_edges), 058 (vendor_records), 030+035
(interview_extractions has org_id; cols: org_id, engagement_id, participant_id,
interview_id, kind, transcript_hash, extraction JSONB NOT NULL, created_at).

### Risks
- Enum drift: must use ONLY the allowed CHECK values per table. Mitigation: bake exact enums.
- FK ordering: insert parents before children, clause before obligation referencing it.
- interview_extractions UNIQUE(org_id,interview_id,kind); upsert/delete by org+eng.
- vendor_records NOT NULL: org_id, engagement_id, vendor_id, name. spend_type/kraljic/lock_in_risk are CHECK-constrained enums.
- Idempotency: DELETE must cascade in correct order (edges/obligations/clauses/versions/parties/contracts/vendor_records/interview_extractions) scoped to org+eng.

## Criteria

- [ ] ISC-1: Script saved to exact target path
- [ ] ISC-2: Connects via process.env.DATABASE_URL only (no hardcoded conn)
- [ ] ISC-3: Uses pg Client/Pool and a single BEGIN/COMMIT transaction
- [ ] ISC-4: crypto.randomUUID() generates ids held in JS vars for FKs
- [ ] ISC-5: Idempotent DELETE for org+eng across all 8 tables before insert
- [ ] ISC-6: interview_extractions visibility row inserted (kind=blueprint)
- [ ] ISC-7: vendor_records row per vendor with NOT NULL + enum-valid cols
- [ ] ISC-8: 6-10 contracts incl parent MSA + child order_form/sow via parent_contract_id
- [ ] ISC-9: contract_versions with exactly one is_current=true per contract
- [ ] ISC-10: contract_clauses present per current version
- [ ] ISC-11: contract_obligations FK source_clause_id to clause of same version
- [ ] ISC-12: contract_parties principal(customer)+counterparty(vendor) per contract
- [ ] ISC-13: 15-25 contract_edges with spread of edge_class values
- [ ] ISC-14: edges include cross_contract, risk, switching, service_depends classes
- [ ] ISC-15: Only allowed enum values used for every CHECK column
- [ ] ISC-16: Summary log of inserted counts at end; script not executed

## Decisions
- silmari: recall returned no cards; bootstrap succeeded. No prior memory for this task.
- Use a single pg Client (not Pool) for clean transaction semantics.
- Marker for idempotency = scoping all deletes by (org_id, engagement_id); interview_extractions by org+engagement+interview_id LIKE 'iv-contract-demo%'.

## Verification
(filled at VERIFY)
