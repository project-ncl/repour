import unittest

import repour.exception

def _yield_matching(ns, end):
   for name in dir(ns):
       if not name == end and name.endswith(end):
           yield getattr(ns, name)

class TestDescribedError(unittest.TestCase):
    def test_children(self):
        for prefix in ["Pull", "Repo", "Adjust"]:
            with self.assertRaises(repour.exception.DescribedError):
                raise getattr(repour.exception, prefix + "Error")("something")

class TestCommandError(unittest.TestCase):
    def test_children(self):
        for child in _yield_matching(repour.exception, "CommandError"):
            with self.assertRaises(repour.exception.CommandError):
                raise child("something", [], 1)
            with self.assertRaises(repour.exception.DescribedError):
                raise child("something", [], 1)
