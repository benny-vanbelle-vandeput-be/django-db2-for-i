Column order of created tables verified (issue #23): `CREATE TABLE` follows
the model's fields (`_meta.local_fields`) exactly, also with fields from
abstract base classes and mixins; Troubleshooting explains why such fields
usually come first, and that `AddField` appends at the end.
