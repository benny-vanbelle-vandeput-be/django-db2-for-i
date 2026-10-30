-- golden: dml/bulk_insert_update_conflicts
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[1, 1, "Db2 for i", 10, 2, 1, "IBM i", 20]]
-- verified: unverified
MERGE INTO "TESTAPP_BOOK" AS TGT USING (VALUES (CAST(%s AS BIGINT), CAST(%s AS INTEGER), CAST(%s AS NVARCHAR(200)), CAST(%s AS INTEGER)), (CAST(%s AS BIGINT), CAST(%s AS INTEGER), CAST(%s AS NVARCHAR(200)), CAST(%s AS INTEGER))) AS SRC ("ID", "AUTHOR_ID", "TITLE", "PAGES") ON (TGT."ID" = SRC."ID") WHEN MATCHED THEN UPDATE SET TGT."TITLE" = SRC."TITLE", TGT."PAGES" = SRC."PAGES" WHEN NOT MATCHED THEN INSERT ("ID", "AUTHOR_ID", "TITLE", "PAGES") VALUES (SRC."ID", SRC."AUTHOR_ID", SRC."TITLE", SRC."PAGES");
