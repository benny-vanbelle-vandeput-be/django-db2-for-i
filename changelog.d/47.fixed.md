The `%`, `**`, `bitand()`, `bitor()`, `bitxor()`, `bitleftshift()` and
`bitrightshift()` operators failed with SQL0104 (Db2 for i has no such
operators). They are written as `MOD`, `POWER`, `BITAND`, `BITOR`, `BITXOR`
and exact shifts; `>>` rounds down like Python (-5 >> 1 = -3).
