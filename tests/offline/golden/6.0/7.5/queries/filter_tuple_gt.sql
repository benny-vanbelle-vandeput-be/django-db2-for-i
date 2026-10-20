-- golden: queries/filter_tuple_gt
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [["a", "a", 1]]
-- verified: unverified
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE ("TESTAPP_CONTACT"."COMPANY" > %s OR ("TESTAPP_CONTACT"."COMPANY" = %s AND "TESTAPP_CONTACT"."ACCOUNT_NUMBER" > %s));
