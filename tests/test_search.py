"""Tests for asynchronous search request generation."""

import unittest

from aniyori.search import SearchGeneration


class SearchGenerationTests(unittest.TestCase):
    def test_new_request_invalidates_older_response(self):
        generation = SearchGeneration()
        first = generation.begin()
        second = generation.begin()

        self.assertFalse(generation.is_current(first))
        self.assertTrue(generation.is_current(second))

    def test_invalidation_discards_pending_response(self):
        generation = SearchGeneration()
        request = generation.begin()

        generation.invalidate()

        self.assertFalse(generation.is_current(request))

    def test_new_request_after_invalidation_is_current(self):
        generation = SearchGeneration()
        generation.invalidate()
        request = generation.begin()

        self.assertTrue(generation.is_current(request))


if __name__ == "__main__":
    unittest.main()
