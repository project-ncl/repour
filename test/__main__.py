import os
import sys
import unittest

if __name__ == "__main__":
    test_dir = os.path.dirname(os.path.realpath(__file__))
    tests = unittest.defaultTestLoader.discover(
        start_dir=test_dir,
    )

    runner = unittest.TextTestRunner()
    results = runner.run(tests)

    # results.failures and results.errors return a list
    sys.exit(len(results.failures) + len(results.errors))
