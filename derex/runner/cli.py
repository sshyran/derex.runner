# -*- coding: utf-8 -*-

"""Console script for derex.runner."""
import os
import sys
import pluggy
from typing import List, Tuple, Dict
from derex.runner.docker import execute_mysql_query
from derex.runner.docker import check_services
from derex.runner.docker import reset_mysql
from derex.runner.docker import wait_for_mysql
from derex.runner.docker import is_docker_working
from derex.runner.docker import load_dump
from derex.runner.docker import create_deps
from derex.runner.plugins import ConfigSpec
from derex.runner.config import BaseConfig
import logging
import click

from compose.cli.main import main


logger = logging.getLogger(__name__)


COMPOSE_EXTRA_OPTS: List[str] = []


def setup_logging():
    logging.basicConfig()
    for logger in ("urllib3.connectionpool", "compose", "docker"):
        logging.getLogger(logger).setLevel(logging.WARN)
    logging.getLogger("").setLevel(logging.INFO)


def setup_plugin_manager():
    plugin_manager = pluggy.PluginManager("derex.runner")
    plugin_manager.add_hookspecs(ConfigSpec)
    plugin_manager.load_setuptools_entrypoints("derex.runner")
    plugin_manager.register(BaseConfig())
    return plugin_manager


def run_compose(args: List[str], variant: str = "services", dry_run: bool = False):
    create_deps()

    try:
        plugin_manager = setup_plugin_manager()
        settings: Dict = {variant: []}
        for plugin in reversed(list(plugin_manager.get_plugins())):
            plugin_settings = plugin.settings().get(variant)
            if plugin_settings:
                click.echo(f"Loading {plugin.__class__.__name__}")
                settings[variant].extend(plugin_settings())
    except Exception as e:
        click.echo(click.style("Can't load yaml options from settings", fg="red"))
        raise e

    old_argv = sys.argv
    try:
        sys.argv = ["docker-compose"] + settings[variant] + COMPOSE_EXTRA_OPTS + args
        if not dry_run:
            click.echo(f'Running {" ".join(sys.argv)}')
            main()
        else:
            click.echo("Would have run")
            click.echo(click.style(" ".join(sys.argv), fg="blue"))
    finally:
        sys.argv = old_argv


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("compose_args", nargs=-1)
@click.option(
    "--reset-mailslurper",
    default=False,
    is_flag=True,
    help="Resets mailslurper database",
)
@click.option(
    "--dry-run",
    default=False,
    is_flag=True,
    help="Don't actually do anything, just print what would have been run",
)
def ddc(compose_args: Tuple[str, ...], reset_mailslurper: bool, dry_run: bool):
    """Derex docker-compose: run docker-compose with additional parameters.
    Adds docker compose file paths for services and administrative tools.
    If the environment variable DEREX_ADMIN_SERVICES is set to a falsey value,
    only the core ones will be started (mysql, mongodb etc).
    """
    check_docker()
    setup_logging()
    if reset_mailslurper:
        if not check_services(["mysql"]):
            click.echo("Mysql not found.\nMaybe you forgot to run\nddc up -d")
            return 1
        resetmailslurper()
        return 0
    run_compose(list(compose_args), dry_run=dry_run)
    return 0


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("compose_args", nargs=-1)
@click.option(
    "--reset-mysql", default=False, is_flag=True, help="Resets the MySQL database"
)
@click.option(
    "--dry-run",
    default=False,
    is_flag=True,
    help="Don't actually do anything, just print what would have been run",
)
def ddc_ironwood(compose_args: Tuple[str, ...], reset_mysql: bool, dry_run: bool):
    """Derex docker-compose running ironwood files: run docker-compose
    with additional parameters.
    Adds docker compose file paths for edx ironwood daemons.
    """
    check_docker()
    setup_logging()

    if not check_services(["mysql", "mongodb", "rabbitmq"]) and any(
        param in compose_args for param in ["up", "start"]
    ):
        click.echo("Mysql/mongo/rabbitmq services not found.")
        click.echo("Maybe you forgot to run")
        click.echo("ddc up -d")
        return -1

    if reset_mysql:
        resetdb()
        return 0

    run_compose(list(compose_args), variant="openedx", dry_run=dry_run)
    return 0


def resetdb():
    """Reset the mysql database of LMS/CMS
    """
    wait_for_mysql()
    execute_mysql_query("CREATE DATABASE IF NOT EXISTS derex")
    reset_mysql()


def resetmailslurper():
    wait_for_mysql()
    execute_mysql_query("DROP DATABASE IF EXISTS mailslurper")
    load_dump("fixtures/mailslurper.sql")


def check_docker():
    if not is_docker_working():
        click.echo(click.style("Could not connect to docker.", fg="red"))
        click.echo(
            "Is it installed and running? Make sure the docker command works and try again."
        )
        sys.exit(1)
