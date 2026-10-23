SQL that ends in `;` (raw SQL in user code and in Django's tests) no longer
fails with SQL0104: the cursor removes one trailing `;`, as Django's Oracle
backend does.
