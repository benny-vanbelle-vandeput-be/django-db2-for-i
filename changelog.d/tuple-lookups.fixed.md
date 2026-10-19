A string `Value` longer than its field's `max_length` (also a value in a
lookup on a multi-column relation) was cast to the field's length and failed
with CWB0111; it now gets a type of its own length, so the comparison matches
nothing and a selected value comes back whole. Nothing is ever cut short.
