-- golden: queries/filter_tuple_exact
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_account, ddl/create_contact
-- params: [["a", 1]]
-- verified: unverified
SELECT "TESTAPP_CONTACT"."ID", "TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FROM "TESTAPP_CONTACT" WHERE ("TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER") = (CAST(%s AS NVARCHAR(1)), CAST(%s AS INTEGER));
