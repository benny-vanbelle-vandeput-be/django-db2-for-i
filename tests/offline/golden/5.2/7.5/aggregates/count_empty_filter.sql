-- golden: aggregates/count_empty_filter
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT COUNT(CAST(NULL AS BIGINT)) AS "X" FROM "TESTAPP_AUTHOR" LEFT OUTER JOIN "TESTAPP_BOOK" ON ("TESTAPP_AUTHOR"."ID" = "TESTAPP_BOOK"."AUTHOR_ID") GROUP BY "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME";
