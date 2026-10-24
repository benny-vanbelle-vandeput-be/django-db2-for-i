-- golden: ddl/rename_table
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_switch
-- params: [[], []]
-- verified: unverified
RENAME TABLE "TESTAPP_SWITCH" TO "TESTAPP_LIGHTSWITCH";
RENAME TABLE "TESTAPP_LIGHTSWITCH" TO "TESTAPP_SWITCH";
