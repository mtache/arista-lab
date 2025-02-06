from enum import Enum
from typing import Literal
import nornir
import click
import yaml
import sys

import logging
from rich.console import Console
from pathlib import Path
from nornir.core.filter import F
from rich.logging import RichHandler

from arista_lab import config, ceos, docker
import arista_lab.config.interfaces
import arista_lab.config.peering

console = Console()


class Log(str, Enum):
    """Represent log levels from logging module as immutable strings."""

    CRITICAL = logging.getLevelName(logging.CRITICAL)
    ERROR = logging.getLevelName(logging.ERROR)
    WARNING = logging.getLevelName(logging.WARNING)
    INFO = logging.getLevelName(logging.INFO)
    DEBUG = logging.getLevelName(logging.DEBUG)


LogLevel = Literal[Log.CRITICAL, Log.ERROR, Log.WARNING, Log.INFO, Log.DEBUG]


def setup_logging(level: LogLevel = Log.INFO, file: Path | None = None) -> None:
    """Configure logging for Python.

    If a file is provided, logs will also be sent to the file in addition to stdout.
    If a file is provided and logging level is DEBUG, only the logging level INFO and higher will
    be logged to stdout while all levels will be logged in the file.

    Args:
    ----
        level: Python logging level
        file: Send logs to a file

    """
    # Init root logger
    root = logging.getLogger()
    # In ANTA debug mode, level is overridden to DEBUG
    loglevel = getattr(logging, level.upper())
    root.setLevel(loglevel)
    # Silence the logging of chatty Python modules when level is INFO
    if loglevel == logging.INFO:
        # asyncssh is really chatty
        logging.getLogger("pyeapi").setLevel(logging.CRITICAL)
    # Add RichHandler for stdout
    rich_handler = RichHandler(
        markup=True, rich_tracebacks=True, tracebacks_show_locals=False
    )
    # Show Python module in stdout at DEBUG level
    fmt_string = (
        "[grey58]\\[%(name)s][/grey58] %(message)s"
        if loglevel == logging.DEBUG
        else "%(message)s"
    )
    formatter = logging.Formatter(fmt=fmt_string, datefmt="[%X]")
    rich_handler.setFormatter(formatter)
    root.addHandler(rich_handler)
    # Add FileHandler if file is provided
    if file:
        file_handler = logging.FileHandler(file)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        # If level is DEBUG and file is provided, do not send DEBUG level to stdout
        if loglevel == logging.DEBUG:
            rich_handler.setLevel(logging.INFO)


def _init_nornir(ctx: click.Context, param, value) -> nornir.core.Nornir:
    try:
        return nornir.InitNornir(config_file=value, core={"raise_on_error": False})
    except Exception as exc:
        ctx.fail(f"Unable to initialize Nornir with config file '{value}': {str(exc)}")


@click.group()
@click.option(
    "-n",
    "--nornir",
    "nornir",
    default="nornir.yaml",
    type=click.Path(exists=True),
    callback=_init_nornir,
    show_default=True,
    help="Nornir configuration in YAML format.",
)
@click.option(
    "--log-file",
    help="Send the logs to a file. If logging level is DEBUG, only INFO or higher will be sent to stdout.",
    show_envvar=True,
    type=click.Path(file_okay=True, dir_okay=False, writable=True, path_type=Path),
)
@click.option(
    "--log-level",
    "-l",
    help="Python logging level",
    default=logging.getLevelName(logging.INFO),
    show_envvar=True,
    show_default=True,
    type=click.Choice(
        [Log.CRITICAL, Log.ERROR, Log.WARNING, Log.INFO, Log.DEBUG],
        case_sensitive=False,
    ),
)
@click.pass_context
def cli(ctx, nornir: nornir.core.Nornir, log_level: LogLevel, log_file: Path) -> None:
    ctx.ensure_object(dict)
    ctx.obj["nornir"] = nornir
    setup_logging(log_level, log_file)

@cli.command(help="Create or delete device configuration backups to flash")
@click.pass_obj
@click.option(
    "--delete/--no-delete",
    default=False,
    help="Delete the backup on the device flash",
    show_default=True,
)
def backup(obj: dict, delete: bool) -> None:
    if delete:
        config.delete_backups(obj["nornir"])
    else:
        config.create_backups(obj["nornir"])


@cli.command(help="Restore configuration backups from flash")
@click.pass_obj
def restore(obj: dict) -> None:
    config.restore_backups(obj["nornir"])

@cli.command(help="Save configuration to a folder")
@click.pass_obj
@click.option(
    "--folder",
    "folder",
    type=click.Path(writable=True, path_type=Path),
    required=True,
    help="Configuration backup folder",
)
def save(obj: dict, folder: Path) -> None:
    config.save(obj["nornir"], folder)

@cli.command(help="Load configuration from a folder")
@click.pass_obj
@click.option(
    "--folder",
    "folder",
    type=click.Path(writable=True, path_type=Path),
    required=True,
    help="Configuration backup folder",
)
@click.option(
    "--replace/--merge",
    default=False,
    show_default=True,
    help="Replace or merge the configuration on the device",
)
def load(obj: dict, folder: Path, replace: bool) -> None:
    config.create_backups(obj["nornir"])
    config.load(obj["nornir"], folder, replace=replace)

@cli.command(help="Apply configuration templates")
@click.pass_obj
@click.option(
    "--folder",
    "folder",
    type=click.Path(writable=True, path_type=Path),
    required=True,
    help="Configuration template folder",
)
@click.option(
    "--groups/--no-groups",
    default=False,
    show_default=True,
    help="The template folder contains subfolders with Nornir group names",
)
@click.option(
    "--replace/--merge",
    default=False,
    show_default=True,
    help="Replace or merge the configuration on the device",
)
def apply(obj: dict, folder: Path, groups: bool, replace: bool) -> None:
    config.create_backups(obj["nornir"])
    config.apply_templates(obj["nornir"], folder, replace=replace, groups=groups)

@cli.command(help="Configure point-to-point interfaces")
@click.pass_obj
@click.option(
    "--links",
    "links",
    type=click.Path(exists=True, readable=True, path_type=Path),
    required=True,
    help="YAML File describing lab links",
)
def interfaces(obj: dict, links: Path) -> None:
    config.create_backups(obj["nornir"])
    arista_lab.config.interfaces.configure(obj["nornir"], links)

@cli.command(help="Configure peering devices")
@click.pass_obj
@click.option(
    "--group", "group", type=str, required=True, help="Nornir group of peering devices"
)
@click.option(
    "--backbone",
    "backbone",
    type=str,
    required=True,
    help="Nornir group of the backbone",
)
def peering(obj: dict, group: str, backbone: str) -> None:
    config.create_backups(obj["nornir"].filter(F(groups__contains=group)))
    arista_lab.config.peering.configure(obj["nornir"], group, backbone)


def main() -> None:
    try:
        sys.exit(cli(max_content_width=120))
    except Exception:
        console.print_exception()
        sys.exit(1)
