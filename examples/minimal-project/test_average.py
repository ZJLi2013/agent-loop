import unittest

from average import average


class AverageTest(unittest.TestCase):
    def test_fractional_mean(self):
        self.assertEqual(average([1, 2]), 1.5)

    def test_empty_input(self):
        with self.assertRaises(ValueError):
            average([])


if __name__ == "__main__":
    unittest.main()
