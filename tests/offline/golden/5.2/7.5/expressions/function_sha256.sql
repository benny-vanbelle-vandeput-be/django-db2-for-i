-- golden: expressions/function_sha256
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: unverified
SELECT LOWER(HEX(HASH_SHA256(CAST("TESTAPP_AUTHOR"."NAME" AS CLOB(2G) CCSID 1208)))) AS "X" FROM "TESTAPP_AUTHOR";
