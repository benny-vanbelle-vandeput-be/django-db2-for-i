A deferred statement of a migration that fails (for example an index the
database refuses) now rolls the migration's transaction back. Before, the
connection stayed inside the transaction, and later statements failed with
"Attempt to use a closed connection".
