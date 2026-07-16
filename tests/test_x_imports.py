# -*- coding: utf-8 -*-
"""Regression tests for lazy X package exports."""

import subprocess
import sys


def test_x_modules_import_in_both_public_orders():
    code = """
from api.services.x.collection_service import XCollectionService
from media_platform.x.client import XApiClient
from media_platform.x import XOfficialApiCrawler
assert XCollectionService
assert XApiClient
assert XOfficialApiCrawler
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
