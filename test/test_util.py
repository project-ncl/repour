import unittest
import repour.adjust.util as util

class TestUtil(unittest.TestCase):


    def test_get_jvm_from_extra_parameters(self):

        extra_params = ['-DRepour_Java=1.8.0', 'not appropriate']
        jvm = util.get_jvm_from_extra_parameters(extra_params)

        self.assertEqual('1.8.0', jvm)

        extra_params = ['not really', 'not appropriate']

        jvm_not_specified = util.get_jvm_from_extra_parameters(extra_params)
        self.assertEqual(None, jvm_not_specified) 