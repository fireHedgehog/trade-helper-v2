# Schema

Authoritative, ordered SQL migrations for the SQLite database. This folder
is the single source of truth for the database structure — the backend does
not define tables anywhere else.

## Rules

- One file per migration, named `NNNN_short_description.sql` (zero-padded,
  strictly increasing). Never edit a migration that has shipped; add a new one.
- Each file is plain SQLite DDL/DML. It is executed as a single script inside
  one transaction by the migration runner (`backend/app/db/migrator.py`).
- Applied versions are tracked in the `schema_migrations` table. The runner
  applies every pending file in order on backend startup.
- Every table is disposable by design: dropping `database/trade_helper.sqlite3`
  and restarting rebuilds the structure from these files. Only fetched/entered
  data is lost, and all of it is re-fetchable.

## Migrating data

Because the schema lives here as flat SQL, a data migration is: write the new
`NNNN_*.sql` (add/alter/backfill), restart the backend, done. To move the
whole database to another machine, copy `database/trade_helper.sqlite3`; to
rebuild empty, delete it.
