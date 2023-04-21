import unittest
import requests
import base64
import time
import json
import re

from logger_config import logger


class TestSubmitSurvey(unittest.TestCase):
    post_survey_endpoint = "https://demo.com"
    tracking_endpoint = "https://demo.com"

    username = "demo"
    password = "demo"
    header_credentials = f"{base64.b64encode(f'{username}:{password}'.encode()).decode()}"

    customer_id = "demo"

    # although longer implicit waiting could be replaced by sending extra requests, checking if the expected number of items were created and re-running again if not
    # we would need to implement some smaller waits in between each try anyway, probably in a loop and send a request each second or so
    # I tried such solution in the past, and it wasn't really whole lot better... creating way too many requests that
    # could in some cases lead to blacklisting, throttling or just putting unnecessary load on servers...
    # so reasonable implicit wait seems to be on place, I'm very much opened to discuss the best solution from you perspective
    await_records_created = 5

    # define enums + custom favorite_movie values
    color = ["Blue", "Green", "Yellow", "Red"]
    music_genre = ["Pop", "Rock", "Classical", "Jazz", "Punk", "Techno"]
    rating = [1, 2, 3, 4, 5]
    favorite_movie = ["Shrek", "Shrek_2", "Shrek_3", "Shrek_4", "Shrek_5", "Shrek_6"]

    """
    Getting number of events from tracking endpoint before we create new ones, to later compare, 
    if requests which are submitting the surveys actually generate records at tracking endpoint
    - tracking check can be handled by timestamp checking as well, but from my POV requires more code and work. Basic idea outlines:
        a) get and save timestamp from last event before submitting survey -> for each submit, check that the new last timestamp is greater than the saved one
        b) create own timestamp with unix time each time we submit a survey -> get last event timestamp -> round timestamps and compare
    """
    def setUp(self):
        self.number_of_events_before = self.run_get_tracking_response()

    """
    Getting csrf with regex and session token from response, then we are defining headers and payload and 
    posting the request (submitting the survey)
    """
    def run_submit_survey(self, color=None, music_genre=None, rating=None, favorite_movie=None, multiple_answers=False):
        try:
            response = requests.get(url=self.post_survey_endpoint)
        except Exception:
            logger.error("Survey GET request failed")
            raise

        match = re.search(r'name="csrf_token" type="hidden" value="([^"]*)"', response.text)
        logger.error("CSRF token not found within response") if match is None else None

        csrf_token = match.group(1)  # to extract only the captured group between the parenthesis
        session_token = response.cookies.get("session")

        headers = {
            "Cookie": "session=" + session_token,
        }

        payload = {
            "question-0": color,
            "question-1": music_genre,
            "question-2": rating,
            "csrf_token": csrf_token,
            "question-3": favorite_movie}

        if multiple_answers is True:
            payload["question-1"] = [self.music_genre[4], self.music_genre[5], self.music_genre[2]]

        try:
            response = requests.post(self.post_survey_endpoint, headers=headers, data=payload)
            return response
        except Exception:
            logger.error(f"Survey POST request failed")
            raise

    """Receiving response from tracking endpoint and returning number of current events"""
    def run_get_tracking_response(self):
        payload = {"customer_ids": {"registered": self.customer_id}}
        headers = {
            "accept": "application/json",
            "authorization": f"Basic {self.header_credentials}",
            "Content-type": "application/json"
        }

        try:
            tracking_response = requests.post(self.tracking_endpoint, json=payload, headers=headers)
        except Exception:
            logger.error("Tracking POST request failed")
            raise

        number_of_events = len(json.loads(tracking_response.content)["events"])
        return number_of_events

    def assert_survey_successfully_submitted(self, response, expected_text):
        try:
            assert expected_text in response.text
        except AssertionError:
            logger.error(f"'{expected_text}' was expected in the response, but couldn't be found")
            raise

    def assert_items_are_created_at_tracking_endpoint(self, items_created):
        time.sleep(self.await_records_created)
        number_of_events_after = self.run_get_tracking_response()
        new_items_found_via_tracking_endpoint = number_of_events_after - self.number_of_events_before

        try:
            assert new_items_found_via_tracking_endpoint == items_created
        except AssertionError:
            logger.error(f"Number of created events should be {items_created}, but found {new_items_found_via_tracking_endpoint} new items from tracking endpoint only")
            raise

    """
    Tests that all the answer enums showed by FE are properly accepted by BE
    and that unrequired question (favorite movie) accepts standard custom string as an answer
    """
    def test_all_questions_are_answerable_and_all_items_are_usable(self):
        longest_list = max(len(self.color), len(self.music_genre), len(self.rating), len(self.favorite_movie))

        for i in range(longest_list):
            color = self.color[i % len(self.color)]
            music_genre = self.music_genre[i % len(self.music_genre)]
            rating = self.rating[i % len(self.rating)]
            favorite_movie = self.favorite_movie[i % len(self.favorite_movie)]

            response = self.run_submit_survey(color=color, music_genre=music_genre, rating=rating,
                                              favorite_movie=favorite_movie)
            self.assert_survey_successfully_submitted(response, "Your survey was successfully submitted")

        self.assert_items_are_created_at_tracking_endpoint(items_created=24)

    """Tests that unrequired question (favorite movie) can be skipped"""
    def test_unrequired_question_can_be_skipped(self):
        response = self.run_submit_survey(color=self.color[0], music_genre=self.music_genre[0], rating=self.rating[0])

        self.assert_survey_successfully_submitted(response, "Your survey was successfully submitted")
        self.assert_items_are_created_at_tracking_endpoint(items_created=4)

    """Tests that the multiple answer question (music genre) actually accepts multiple answers"""
    def test_multiple_answer_question_accepts_multiple_answers(self):
        response = self.run_submit_survey(color=self.color[0], rating=self.rating[0],
                                          favorite_movie=self.favorite_movie[0], multiple_answers=True)

        self.assert_survey_successfully_submitted(response, "Your survey was successfully submitted")
        self.assert_items_are_created_at_tracking_endpoint(items_created=4)

    """
    We are creating a list of dictionaries where each dictionary represents a pack of arguments inside of another dictionary
    Later we loop over the defined variants and execute the run method with given arguments
    This way, we are testing that each required question throws the error if skipped
    """
    def test_required_questions_cannot_be_skipped(self):
        test_cases = [
            {"params": {"music_genre": self.music_genre[0], "rating": self.rating[0]}},
            {"params": {"color": self.color[0], "rating": self.rating[0]}},
            {"params": {"color": self.color[0], "music_genre": self.music_genre[0]}},
        ]

        self.number_of_events_before = self.run_get_tracking_response()

        for test_case in test_cases:
            response = self.run_submit_survey(**test_case["params"])

            self.assert_survey_successfully_submitted(response, "This field is required")
        self.assert_items_are_created_at_tracking_endpoint(items_created=0)

    """TASK 2: Think about what other scenarios could be tested and define at least 3 such test scenarios in
    writing. You do not need to implement these tests. 
    
    1) test inserting some custom values that do not match expected enums, like sending in:
    "question-0": "Grey",
    "question-1": "Reggae",
    "question-2": 8
    
    2) if we wanted to go for coverage, we could test different combinations of answers across the questions
    (Which doesn't mean I would advise it in this case. In fact, the amount of possible combinations is extreme in 
    comparison to very little benefit, but such move can have its place when combinations are few and feature is crucial)
    
    3) we could test some edge cases, like inputting unexpected values (long, special characters, only spaces, multiple lines) 
    into the favorite movie input box and then checking whether the answer was accepted
    
    4) test proper exceptions are returned when different server failures occur
    (for example typical "Something went wrong, try again in few minutes" when there is some problem,
    typically I'm used to be given a list of custom exceptions implemented in the feature to cover these paths)
    
    5) also, from big picture perspective, it's best practice to set up everything we need to run these tests and not rely on existing data,
    therefore I would also suggest to create survey and obtain its link from the Customer Export Endpoint,
    using one time (class level) setup method before all tests are run, and then use it within the tests
    After all test have been run, the created survey would be deleted from database as class level tear down, using SQL query
    Broader test cases regarding creation of surveys and obtaining it's link would be covered in separate test files
    
    6) posting request without CSRF token
    
    7) These are all BE tests, we could also create some UI tests to verify that FE also acts as expected, for example:
       a) check general interaction with elements
       b) check redirection to the "Survey successfully submitted" after successful submit
       c) check if question wrapper error pops up when we skip required question
       That would be done in different repository though
    """
