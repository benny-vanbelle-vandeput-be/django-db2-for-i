`supports_index_column_ordering`: an index on `Index(fields=["-field"])` is
created with `DESC` (until now the order was dropped), and introspection
reports each column's order.
