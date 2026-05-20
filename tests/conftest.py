import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_runtest_setup(item):
    item._shuffle_patch = patch("keypal.scheduler.random.shuffle", lambda x: None)
    item._shuffle_patch.start()


def pytest_runtest_teardown(item, nextitem):
    item._shuffle_patch.stop()
