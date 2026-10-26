Migrations can now drop columns, narrow them and make them `NOT NULL`
without a system reply list entry: while a migration removes or alters a
field, the backend suppresses inquiry message CPA32B2 for its own job
(`QSYS2.OVERRIDE_QAQQINI`, query option `SUPPRESS_INQUIRY_MESSAGES`) and
turns it back on when the migration is done. A narrowing change that would
truncate a string or round a number is refused with `DataError` first. New
option `OPTIONS["suppress_inquiry_messages"]` (default `True`); `False` keeps
CPA32B2 for migrations too. `RunSQL` and your own cursors keep CPA32B2.
