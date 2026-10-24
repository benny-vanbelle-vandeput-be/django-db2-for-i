An `AlterField` that changes or removes the check of a positive integer
field (for example `PositiveIntegerField` to `IntegerField`) failed with
`SQL0199 - Keyword NONE not expected`; it now drops the check (#151).
