from derex.runner.utils import CONF_FILENAME
from derex.runner.utils import get_dir_hash
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Optional
from typing import Union

import hashlib
import os
import yaml


logger = getLogger(__name__)


class ProjectRunMode(Enum):
    debug = "debug"  # The first is the default
    production = "production"


class Project:
    """Represents a derex.runner project, i.e. a directory with a
    `derex.config.yaml` file and optionally a "themes", "settings" and
    "requirements" directory.
    """

    #: The root path to this project
    root: Path

    #: The tag of the base image with dev goodies and precompiled assets
    base_image: str

    # Tne image tag of the base image for the final production project build
    final_base_image: str

    #: The directory containing requirements, if defined
    requirements_dir: Optional[Path] = None

    #: The directory containing themes, if defined
    themes_dir: Optional[Path] = None

    # The directory containing project settings (that feed django.conf.settings)
    settings_dir: Optional[Path] = None

    # The directory containing project database fixtures (used on --reset-mysql)
    fixtures_dir: Optional[Path] = None

    # The image tag of the image that includes requirements
    requirements_image_tag: str

    # The image tag of the image that includes requirements and themes
    themes_image_tag: str

    # The image tag of the final image containing everything needed for this project
    image_tag: str

    # Name of the database this project uses
    mysql_db_name: str

    # Path to a local docker-compose.yml file, if present
    local_compose: Optional[Path] = None

    @property
    def runmode(self) -> ProjectRunMode:
        """The run mode of this project, either debug or production.
        In debug mode django's runserver is used. Templates are reloaded
        on every request and assets do not need to be collected.
        In production mode gunicorn is run, and assets need to be compiled and collected.
        """
        name = "runmode"
        mode_str = self._get_status(name)
        if mode_str is not None:
            if mode_str in ProjectRunMode.__members__:
                return ProjectRunMode[mode_str]
            # We found a string but we don't recognize it: warn the user
            logger.warn(
                f"Value `{mode_str}` found in `{self._status_filepath(name)}` "
                "is not valid for runmode "
                "(valid values are `debug` and `production`)"
            )
        default = self.config.get(f"default_{name}")
        if default:
            if default not in ProjectRunMode.__members__:
                logger.warn(
                    f"Value `{default}` found in config `{self.root / CONF_FILENAME}` "
                    "is not a valid default for runmode "
                    "(valid values are `debug` and `production`)"
                )
            else:
                return ProjectRunMode[default]
        return next(iter(ProjectRunMode))  # Return the first by default

    @runmode.setter
    def runmode(self, value: ProjectRunMode):
        self._set_status("runmode", value.name)

    def _get_status(self, name: str) -> Optional[str]:
        """Read value for the desired status from the project directory.
        """
        filepath = self._status_filepath(name)
        if filepath.exists():
            return filepath.read_text()
        return None

    def _set_status(self, name: str, value: str):
        """Persist a status in the project directory
        """
        self._status_filepath(name).write_text(value)

    def _status_filepath(self, name: str) -> Path:
        """Return the full file path where a status for the project should be stored
        """
        return self.root / name

    def __init__(self, path: Union[Path, str] = None):
        if not path:
            path = os.getcwd()
        self.root = find_project_root(Path(path))
        config_path = self.root / CONF_FILENAME
        self.config = yaml.load(config_path.open())
        self.base_image = self.config.get("base_image", "derex/openedx-ironwood:latest")
        self.final_base_image = self.config.get(
            "final_base_image", "derex/openedx-nostatic:latest"
        )
        if "project_name" not in self.config:
            raise ValueError(f"A project_name was not specified in {config_path}")
        self.name = self.config["project_name"]
        local_compose = self.root / "docker-compose.yml"
        if local_compose.is_file():
            self.local_compose = local_compose

        requirements_dir = self.root / "requirements"
        if requirements_dir.is_dir():
            self.requirements_dir = requirements_dir
            # We only hash text files inside the requirements image:
            # this way changes to code can be made effective by
            # mounting the requirements directory
            img_hash = get_requirements_hash(self.requirements_dir)
            self.requirements_image_tag = (
                f"{self.name}/openedx-requirements:{img_hash[:6]}"
            )
        else:
            self.requirements_image_tag = self.base_image

        themes_dir = self.root / "themes"
        if themes_dir.is_dir():
            self.themes_dir = themes_dir
            img_hash = get_dir_hash(
                self.themes_dir
            )  # XXX some files are generated. We should ignore them when we hash the directory
            self.themes_image_tag = f"{self.name}/openedx-themes:{img_hash[:6]}"
        else:
            self.themes_image_tag = self.requirements_image_tag

        settings_dir = self.root / "settings"
        if settings_dir.is_dir():
            self.settings_dir = settings_dir
            # TODO: run some sanity checks on the settings dir and raise an
            # exception if they fail

        fixtures_dir = self.root / "fixtures"
        if fixtures_dir.is_dir():
            self.fixtures_dir = fixtures_dir

        self.image_tag = self.themes_image_tag
        self.mysql_db_name = self.config.get("mysql_db_name", f"{self.name}_edxapp")


def get_requirements_hash(path: Path) -> str:
    """Given a directory, return a hash of the contents of the text files it contains.
    """
    hasher = hashlib.sha256()
    for file in path.iterdir():
        if file.is_file():
            hasher.update(file.read_bytes())
    return hasher.hexdigest()


def find_project_root(path: Path) -> Path:
    """Find the project directory walking up the filesystem starting on the
    given path until a configuration file is found.
    """
    current = path
    while current != current.parent:
        if (current / CONF_FILENAME).is_file():
            return current
        current = current.parent
    raise ValueError(
        f"No directory found with a {CONF_FILENAME} file in it, starting from {path}"
    )
