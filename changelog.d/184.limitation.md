A `CheckConstraint` that matches a column against a pattern built from
another column (for example `~Q(surname__startswith=F("name"))`) is
refused by Db2 for i (SQL0546); patterns with a constant work. See Known
Limitations.
