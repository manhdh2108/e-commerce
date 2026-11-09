# OLTP data export

`mock_oltp.dump` is a `pg_dump --format=custom` snapshot of the `mock_oltp` PostgreSQL
database (33 business tables from the mock platform), taken 2026-11-09.

## Restore

```bash
createdb mock_oltp_restored
pg_restore --no-owner --no-privileges -d mock_oltp_restored data/oltp_export/mock_oltp.dump
```

Or into an existing database:

```bash
pg_restore --no-owner --no-privileges -d mock_oltp data/oltp_export/mock_oltp.dump
```

## Regenerate

```bash
PGPASSWORD=local_mock_only pg_dump -h 127.0.0.1 -p 55432 -U mock -d mock_oltp \
  --format=custom --no-owner --no-privileges -f data/oltp_export/mock_oltp.dump
```

(the `dw_reader` role lacks SELECT on sequences, so dumping must use `mock`, the schema owner)
