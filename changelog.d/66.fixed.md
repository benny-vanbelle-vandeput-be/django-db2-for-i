`bulk_update()` on a ForeignKey or GenericIPAddressField failed with
NotSupportedError ("Value of type ... with output field ForeignKey"): a
ForeignKey value now takes its target field's type (recursively, for a key
to a key; integer, CharField and UUID primary keys), and an IP address is a
VARCHAR(39).
