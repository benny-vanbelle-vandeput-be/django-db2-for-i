-- golden: ddl/add_check_constraint
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_rating
-- params: [[], []]
-- verified: unverified
ALTER TABLE "TESTAPP_RATING" ADD CONSTRAINT "TESTAPP_RATING_STARS_LTE_5" CHECK ("STARS" <= 5);
ALTER TABLE "TESTAPP_RATING" DROP CONSTRAINT "TESTAPP_RATING_STARS_LTE_5";
