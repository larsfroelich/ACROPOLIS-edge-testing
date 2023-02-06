"""
if not a version upgrade:
1. test new config on local hardware
2. if tests unsuccessful: send errors per mqtt, keep old config, exit
3. save new config version

if version upgrade
1. Download the new version into the respective directory
2. Create new .venv
3. Install new dependencies
4. Run tests
5. if tests unsuccessful: send errors per mqtt, keep old config, exit
6. Update the `insert-name-here-cli.sh` to point to the new version
7. Call `insert-name-here-cli start` using the `at in 1 minute` command
8. Call `sys.exit()`
"""

import json
import os
import shutil
from typing import Callable
from src import custom_types, utils

NAME = "hermes"
REPOSITORY = f"tum-esm/{NAME}"
ROOT_PATH = f"{os.environ['HOME']}/Documents/{NAME}"

tarball_name: Callable[[str], str] = lambda version: f"v{version}.tar.gz"
tarball_content_name: Callable[[str], str] = lambda version: f"{NAME}-{version}"
code_path: Callable[[str], str] = lambda version: f"{ROOT_PATH}/{version}"
venv_path: Callable[[str], str] = lambda version: f"{ROOT_PATH}/{version}/.venv"

dirname = os.path.dirname
PROJECT_DIR = dirname(dirname(dirname(os.path.abspath(__file__))))
CURRENT_CONFIG_PATH = os.path.join(PROJECT_DIR, "config", "config.json")
CURRENT_TMP_CONFIG_PATH = os.path.join(PROJECT_DIR, "config", "config.tmp.json")


def clear_path(path: str) -> bool:
    """remove a file or directory, returns true if it existed"""
    if os.path.isfile(path):
        os.remove(path)
        return True
    if os.path.isdir(path):
        shutil.rmtree(path)
        return True
    return False


# TODO: do not try an upgrade to a specific revision twice


def store_current_config() -> None:
    if os.path.isfile(CURRENT_TMP_CONFIG_PATH):
        os.remove(CURRENT_TMP_CONFIG_PATH)
    os.rename(CURRENT_CONFIG_PATH, CURRENT_TMP_CONFIG_PATH)


def restore_current_config() -> None:
    if os.path.isfile(CURRENT_CONFIG_PATH):
        os.remove(CURRENT_CONFIG_PATH)
    os.rename(CURRENT_TMP_CONFIG_PATH, CURRENT_CONFIG_PATH)


class ConfigurationProcedure:
    """runs when a config change has been requested"""

    def __init__(self, config: custom_types.Config) -> None:
        self.logger = utils.Logger(origin="configuration-procedure")
        self.config = config

    def run(self, config_request: custom_types.MQTTConfigurationRequest) -> None:
        new_revision = config_request.revision
        new_version = config_request.configuration.version

        if self.config.revision == new_revision:
            self.logger.info("received config has the same revision")
            return

        has_same_version = self.config.version == new_version
        has_same_directory = PROJECT_DIR == code_path(new_version)

        self.logger.info(
            f"upgrading to new revision {new_revision} and version {new_version} using the"
            + f" new config: {json.dumps(config_request.configuration.dict(), indent=4)}"
        )

        try:
            store_current_config()
            if not (has_same_version and has_same_directory):
                self._download_code(new_version)
                self._set_up_venv(new_version)
                self._dump_new_config(config_request)

            self._run_pytests(new_version)
            self.logger.info(f"tests were successful")

            self._update_cli_pointer(new_version)
            self.logger.info(f"switched CLI pointer successfully")

            restore_current_config()
            exit(0)

        except Exception as e:
            self.logger.error(
                f"exception during upgrade to revision {new_revision}",
                config=self.config,
            )
            self.logger.exception(e, config=self.config)
        finally:
            restore_current_config()

        self.logger.info(
            f"continuing with current revision {self.config.revision} "
            + f"and version {self.config.version}"
        )

    def _download_code(self, version: str) -> None:
        """uses the GitHub CLI to download the code for a specific release"""
        if os.path.isdir(code_path(version)):
            self.logger.info("code directory already exists")
            return

        # download release using the github cli
        self.logger.info("downloading code from GitHub")
        utils.run_shell_command(
            f"wget https://github.com/tum-esm/hermes/archive/refs/tags/{tarball_name(version)}"
        )

        # extract code archive
        self.logger.info("extracting tarball")
        utils.run_shell_command(f"tar -xf {tarball_name(version)}")

        # move sensor subdirectory
        self.logger.info("copying sensor code")
        shutil.move(
            f"{tarball_content_name(version)}/sensor",
            code_path(version),
        )

        # remove download assets
        self.logger.info("removing artifacts")
        os.remove(tarball_name(version))
        shutil.rmtree(tarball_content_name(version))

    def _set_up_venv(self, version: str) -> None:
        """set up a virtual python3.9 environment inside the version subdirectory"""
        if os.path.isdir(venv_path(version)):
            self.logger.info("venv already exists")
            return

        self.logger.info(f"setting up new venv")
        utils.run_shell_command(
            f"python3.9 -m venv .venv",
            working_directory=code_path(version),
        )

        self.logger.info(f"installing dependencies")
        utils.run_shell_command(
            f"source .venv/bin/activate && poetry install",
            working_directory=code_path(version),
        )

    def _dump_new_config(
        self,
        config_request: custom_types.MQTTConfigurationRequest,
    ) -> None:
        """write new config config to json file"""

        self.logger.info("dumping config.json file")
        with open(
            f"{code_path(config_request.configuration.version)}/config/config.json",
            "w",
        ) as f:
            json.dump(
                {
                    "revision": config_request.revision,
                    **config_request.configuration.dict(),
                },
                f,
                indent=4,
            )

        self.logger.info("copying .env file")
        src = f"{PROJECT_DIR}/config/.env"
        dst = f"{code_path(config_request.configuration.version)}/config/.env"
        if not os.path.isfile(dst):
            shutil.copy(src, dst)

    def _run_pytests(self, version: str) -> None:
        """run pytests for the new version. The tests should only ensure that
        the new software starts up and is able to perform new confi requests"""
        self.logger.info("running pytests")
        utils.run_shell_command(
            f'.venv/bin/python -m pytest -m "config_update" tests/',
            working_directory=code_path(version),
        )

    def _update_cli_pointer(self, version: str) -> None:
        """make the file pointing to the used cli to the new version's cli"""
        with open(f"{ROOT_PATH}/{NAME}-cli.sh", "w") as f:
            f.write(
                "set -o errexit\n\n"
                + f"{venv_path(version)}/bin/python "
                + f"{code_path(version)}/cli/main.py $*"
            )
