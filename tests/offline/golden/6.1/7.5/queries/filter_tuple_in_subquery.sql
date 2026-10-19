-- golden: queries/filter_tuple_in_subquery
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [[1]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE ((SELECT (1) AS "A" FROM "TESTAPP_ACCOUNT" "U0" WHERE ("U0"."NUMBER" > %s AND "TESTAPP_CONTACT"."COMPANY" = ("U0"."COMPANY") AND "TESTAPP_CONTACT"."ACCOUNT_NUMBER" = ("U0"."NUMBER")) FETCH FIRST 1 ROWS ONLY) IS NOT NULL);
