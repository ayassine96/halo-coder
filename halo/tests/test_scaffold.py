#!/usr/bin/env python3
"""Stub test to verify halo test discovery works."""


import unittest


class TestHaloScaffold(unittest.TestCase):

    def test_truth(self):
        self.assertTrue(True)

    def test_directory_structure(self):
        import halo
        import halo.factory
        import halo.specs
        import halo.common
        import halo.kernel
        import halo.tdad
        import halo.memory
        import halo.dagger
        import halo.nanoclaw
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()