Closing a cursor that is already closed does nothing, as with Django's other backends; it raised `ProgrammingError` ("Attempt to use a closed cursor").
