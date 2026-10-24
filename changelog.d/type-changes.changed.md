An `AlterField` that changes a column to a type Db2 for i cannot convert in
place (for example text to a date, a number to text, or `DateField` to
`DateTimeField`) raises `NotSupportedError` before any SQL is sent, with the
workaround (new field, data migration, remove the old field); see Known
limitations.
