import pytest
from ..pytest_fixtures import mqtt_client_environment, mqtt_sending_loop, log_files
from os.path import dirname, abspath, join
import sys

PROJECT_DIR = dirname(dirname(dirname(abspath(__file__))))
LOG_FILE = join(PROJECT_DIR, "logs", "current-logs.log")
sys.path.append(PROJECT_DIR)

from src import utils, custom_types


# TODO: test whether logger enqueues and sends mqtt messages


@pytest.mark.dev
@pytest.mark.ci
def test_logger(mqtt_sending_loop: None, log_files: None) -> None:
    config = custom_types.Config(
        **{
            "version": "0.1.0",
            "revision": 17,
            "general": {"station_name": "pytest-dummy-config"},
            "valves": {
                "air_inlets": [
                    {"number": 1, "direction": 300},
                    {"number": 2, "direction": 50},
                ]
            },
        }
    )

    expected_lines = [
        "pytests - DEBUG - some message a",
        "pytests - INFO - some message b",
        "pytests - WARNING - some message c",
        "pytests - ERROR - some message d",
    ]

    with open(LOG_FILE, "r") as f:
        file_content = f.read()
        for l in expected_lines:
            assert l not in file_content

    logger = utils.Logger(origin="pytests")
    logger.debug("some message a")
    logger.info("some message b")
    logger.warning("some message c", config=config)
    logger.error("some message d", config=config)

    with open(LOG_FILE, "r") as f:
        file_content = f.read()
        for l in expected_lines:
            assert l in file_content

    # TODO: assert queue file content (all pending)
    # TODO: sleep
    # TODO: assert archive file content (all sent)
