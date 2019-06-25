import pkg_resources
import os
from compose.cli.main import main
from typing import List
import sys
import logging


def run_compose(args: List[str]):
    old_argv = sys.argv
    try:
        sys.argv = ["docker-compose"] + yaml_opts() + args
        logging.getLogger(__name__).info(f"Running {' '.join(sys.argv)}")
        main()
    finally:
        sys.argv = old_argv


def yaml_opts() -> List[str]:
    """Return a list of strings pointing to docker-compose yml files suitable
    to be passed as options to docker-compose.
    The list looks like:
    ['-f', '/path/to/docker-compose.yml', '-f', '/path/to/another-docker-compose.yml']
    """
    result = [
        "-f",
        pkg_resources.resource_filename(
            __name__, "templates/docker-compose-services.yml"
        ),
    ]
    if asbool(os.environ.get("DEREX_ADMIN_SERVICES", True)):
        result += [
            "-f",
            pkg_resources.resource_filename(
                __name__, "templates/docker-compose-admin.yml"
            ),
        ]
    return result


truthy = frozenset(("t", "true", "y", "yes", "on", "1"))


def asbool(s):
    """ Return the boolean value ``True`` if the case-lowered value of string
    input ``s`` is a :term:`truthy string`. If ``s`` is already one of the
    boolean values ``True`` or ``False``, return it."""
    if s is None:
        return False
    if isinstance(s, bool):
        return s
    s = str(s).strip()
    return s.lower() in truthy


def start_service():
    run_compose(["ps"])