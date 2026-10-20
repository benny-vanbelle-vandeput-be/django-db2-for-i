-- golden: queries/filter_tuple_in_list
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [["a", 1, "b", 2]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE (("TESTAPP_CONTACT"."COMPANY" = %s AND "TESTAPP_CONTACT"."ACCOUNT_NUMBER" = %s) OR ("TESTAPP_CONTACT"."COMPANY" = %s AND "TESTAPP_CONTACT"."ACCOUNT_NUMBER" = %s));
