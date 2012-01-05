"""
Test framework - basic skeleton to simplify loading testsuite-wide
"""
from unittest import TestCase

class TestController(TestCase):

    def __init__(self, *args, **kwargs):
        # Load some config if required...
        TestCase.__init__(self, *args, **kwargs)

    def setUp(self):
        pass
        
    def tearDown(self):
        pass
