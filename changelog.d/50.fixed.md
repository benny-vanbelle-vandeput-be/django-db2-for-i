`Value(<uuid>)` (for example `update(id=Value(uuid))` on a UUIDField)
raised NotSupportedError; it is sent as a typed `CAST(? AS CHAR(32))`
marker, like UUIDField columns.
