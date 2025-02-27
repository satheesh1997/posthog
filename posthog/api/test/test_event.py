import json

from dateutil.relativedelta import relativedelta
from django.utils import timezone
from freezegun import freeze_time

from posthog.models import Action, ActionStep, Element, Event, Person, Team

from .base import BaseTest, TransactionBaseTest


def test_event_api_factory(event_factory, person_factory, action_factory):
    class TestEvents(TransactionBaseTest):
        TESTS_API = True
        ENDPOINT = "event"

        def test_filter_events(self):
            person_factory(
                properties={"email": "tim@posthog.com"}, team=self.team, distinct_ids=["2", "some-random-uid"],
            )

            event_factory(
                event="$autocapture",
                team=self.team,
                distinct_id="2",
                properties={"$ip": "8.8.8.8"},
                elements=[Element(tag_name="button", text="something"), Element(tag_name="div")],
            )
            event_factory(
                event="$pageview", team=self.team, distinct_id="some-random-uid", properties={"$ip": "8.8.8.8"}
            )
            event_factory(
                event="$pageview", team=self.team, distinct_id="some-other-one", properties={"$ip": "8.8.8.8"}
            )

            with self.assertNumQueries(10):
                response = self.client.get("/api/event/?distinct_id=2").json()
            self.assertEqual(response["results"][0]["person"], "tim@posthog.com")
            self.assertEqual(response["results"][0]["elements"][0]["tag_name"], "button")
            self.assertEqual(response["results"][0]["elements"][0]["order"], 0)
            self.assertEqual(response["results"][0]["elements"][1]["order"], 1)

        def test_filter_events_by_event_name(self):
            person_factory(
                properties={"email": "tim@posthog.com"}, team=self.team, distinct_ids=["2", "some-random-uid"],
            )
            event_factory(
                event="event_name", team=self.team, distinct_id="2", properties={"$ip": "8.8.8.8"},
            )
            event_factory(
                event="another event", team=self.team, distinct_id="2", properties={"$ip": "8.8.8.8"},
            )
            with self.assertNumQueries(7):
                response = self.client.get("/api/event/?event=event_name").json()
            self.assertEqual(response["results"][0]["event"], "event_name")

        def test_filter_events_by_properties(self):
            person_factory(
                properties={"email": "tim@posthog.com"}, team=self.team, distinct_ids=["2", "some-random-uid"],
            )
            event_factory(
                event="event_name", team=self.team, distinct_id="2", properties={"$browser": "Chrome"},
            )
            event2 = event_factory(
                event="event_name", team=self.team, distinct_id="2", properties={"$browser": "Safari"},
            )

            with self.assertNumQueries(7):
                response = self.client.get(
                    "/api/event/?properties=%s" % (json.dumps([{"key": "$browser", "value": "Safari"}]))
                ).json()
            self.assertEqual(response["results"][0]["id"], event2.pk)

        def test_filter_by_person(self):
            person = person_factory(
                properties={"email": "tim@posthog.com"}, distinct_ids=["2", "some-random-uid"], team=self.team,
            )

            event_factory(event="random event", team=self.team, distinct_id="2", properties={"$ip": "8.8.8.8"})
            event_factory(
                event="random event", team=self.team, distinct_id="some-random-uid", properties={"$ip": "8.8.8.8"}
            )
            event_factory(
                event="random event", team=self.team, distinct_id="some-other-one", properties={"$ip": "8.8.8.8"}
            )

            response = self.client.get("/api/event/?person_id=%s" % person.pk).json()
            self.assertEqual(len(response["results"]), 2)
            self.assertEqual(response["results"][0]["elements"], [])

        def _signup_event(self, distinct_id: str):
            sign_up = event_factory(
                event="$autocapture",
                distinct_id=distinct_id,
                team=self.team,
                elements=[Element(tag_name="button", text="Sign up!")],
            )
            return sign_up

        def _pay_event(self, distinct_id: str):
            sign_up = event_factory(
                event="$autocapture",
                distinct_id=distinct_id,
                team=self.team,
                elements=[
                    Element(tag_name="button", text="Pay $10"),
                    # check we're not duplicating
                    Element(tag_name="div", text="Sign up!"),
                ],
            )
            return sign_up

        def _movie_event(self, distinct_id: str):
            sign_up = event_factory(
                event="$autocapture",
                distinct_id=distinct_id,
                team=self.team,
                elements=[
                    Element(
                        tag_name="a",
                        attr_class=["watch_movie", "play"],
                        text="Watch now",
                        attr_id="something",
                        href="/movie",
                    ),
                    Element(tag_name="div", href="/movie"),
                ],
            )
            return sign_up

        def test_event_property_values(self):
            event_factory(
                distinct_id="bla",
                event="random event",
                team=self.team,
                properties={"random_prop": "asdf", "some other prop": "with some text"},
            )
            event_factory(distinct_id="bla", event="random event", team=self.team, properties={"random_prop": "asdf"})
            event_factory(distinct_id="bla", event="random event", team=self.team, properties={"random_prop": "qwerty"})
            event_factory(distinct_id="bla", event="random event", team=self.team, properties={"random_prop": True})
            event_factory(distinct_id="bla", event="random event", team=self.team, properties={"random_prop": False})
            event_factory(
                distinct_id="bla",
                event="random event",
                team=self.team,
                properties={"random_prop": {"first_name": "Mary", "last_name": "Smith"}},
            )
            event_factory(
                distinct_id="bla", event="random event", team=self.team, properties={"something_else": "qwerty"}
            )
            event_factory(distinct_id="bla", event="random event", team=self.team, properties={"random_prop": 565})
            team2 = Team.objects.create()
            event_factory(distinct_id="bla", event="random event", team=team2, properties={"random_prop": "abcd"})
            response = self.client.get("/api/event/values/?key=random_prop").json()

            keys = [resp["name"].replace(" ", "") for resp in response]
            self.assertCountEqual(
                keys, ["asdf", "qwerty", "565", "false", "true", '{"first_name":"Mary","last_name":"Smith"}']
            )
            self.assertEqual(len(response), 6)

            response = self.client.get("/api/event/values/?key=random_prop&value=qw").json()
            self.assertEqual(response[0]["name"], "qwerty")

            response = self.client.get("/api/event/values/?key=random_prop&value=6").json()
            self.assertEqual(response[0]["name"], "565")

        def test_before_and_after(self):
            user = self._create_user("tim")
            self.client.force_login(user)
            person_factory(
                properties={"email": "tim@posthog.com"}, team=self.team, distinct_ids=["2", "some-random-uid"],
            )

            with freeze_time("2020-01-10"):
                event1 = event_factory(team=self.team, event="sign up", distinct_id="2")
            with freeze_time("2020-01-8"):
                event2 = event_factory(team=self.team, event="sign up", distinct_id="2")
            with freeze_time("2020-01-7"):
                event3 = event_factory(team=self.team, event="random other event", distinct_id="2")

            action = Action.objects.create(team=self.team)
            ActionStep.objects.create(action=action, event="sign up")
            action.calculate_events()

            response = self.client.get("/api/event/?after=2020-01-09T00:00:00.000Z&action_id=%s" % action.pk).json()
            self.assertEqual(len(response["results"]), 1)
            self.assertEqual(response["results"][0]["id"], event1.pk)

            response = self.client.get("/api/event/?before=2020-01-09T00:00:00.000Z&action_id=%s" % action.pk).json()
            self.assertEqual(len(response["results"]), 1)
            self.assertEqual(response["results"][0]["id"], event2.pk)

            # without action
            response = self.client.get("/api/event/?after=2020-01-09T00:00:00.000Z").json()
            self.assertEqual(len(response["results"]), 1)
            self.assertEqual(response["results"][0]["id"], event1.pk)

            response = self.client.get("/api/event/?before=2020-01-09T00:00:00.000Z").json()
            self.assertEqual(len(response["results"]), 2)
            self.assertEqual(response["results"][0]["id"], event2.pk)
            self.assertEqual(response["results"][1]["id"], event3.pk)

        def test_pagination(self):
            person_factory(team=self.team, distinct_ids=["1"])
            for idx in range(0, 150):
                event_factory(
                    team=self.team,
                    event="some event",
                    distinct_id="1",
                    timestamp=timezone.datetime(2019, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
                    + relativedelta(days=idx, seconds=idx),
                )
            response = self.client.get("/api/event/?distinct_id=1").json()
            self.assertEqual(len(response["results"]), 100)
            self.assertIn("http://testserver/api/event/?distinct_id=1&before=", response["next"])

            page2 = self.client.get(response["next"]).json()
            from posthog.ee import is_ee_enabled

            if is_ee_enabled():
                from ee.clickhouse.client import sync_execute

                self.assertEqual(sync_execute("select count(*) from events")[0][0], 150)

            self.assertEqual(len(page2["results"]), 50)

        def test_action_no_steps(self):
            action = Action.objects.create(team=self.team)
            action.calculate_events()

            response = self.client.get("/api/event/?action_id=%s" % action.pk)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["results"]), 0)

        def test_get_single_action(self):
            event1 = event_factory(team=self.team, event="sign up", distinct_id="2", properties={"key": "test_val"})
            response = self.client.get("/api/event/%s/" % event1.id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["event"], "sign up")
            self.assertEqual(response.json()["properties"], {"key": "test_val"})

    return TestEvents


def _create_action(**kwargs):
    team = kwargs.pop("team")
    name = kwargs.pop("name")
    action = Action.objects.create(team=team, name=name)
    ActionStep.objects.create(action=action, event=name)
    action.calculate_events()
    return action


class TestEvent(test_event_api_factory(Event.objects.create, Person.objects.create, _create_action)):  # type: ignore
    pass
