# Database

Runtime home of the SQLite database file (`trade_helper.sqlite3`). The file
itself is git-ignored — it is disposable and rebuilt from `schema/` on
backend startup.

- To reset: stop the backend, delete `trade_helper.sqlite3`, start the
  backend. The migration runner recreates the structure.
- To move machines: copy `trade_helper.sqlite3` here on the target machine.
- Path is configurable via the backend `DATABASE_PATH` setting; it defaults
  to this folder.
