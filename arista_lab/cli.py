#!/usr/bin/env python
from enum import Enum
import pickle
from typing import Literal
import nornir
import click
import sys

import logging
from rich.console import Console
from pathlib import Path
from nornir.core.filter import F
from rich.logging import RichHandler

import arista_lab.config
import arista_lab.traffic
import arista_lab.config.interfaces
import arista_lab.config.peering
import snappi # type: ignore[import-untyped]

console = Console()

logger = logging.getLogger(__name__)

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
    # Get loggers
    loggers = ["arista_lab", "snappi", "snappi_ixnetwork", "ixnetwork_restpy.connection", "pyeapi"]
    loglevel = getattr(logging, level.upper())
    for logger_name in loggers:
        logging.getLogger(logger_name).setLevel(loglevel)
    # Silence the logging of chatty Python modules when level is INFO
    if loglevel == logging.INFO:
        logging.getLogger("pyeapi").setLevel(logging.CRITICAL)
    # Add RichHandler for stdout
    rich_handler = RichHandler(rich_tracebacks=True, tracebacks_show_locals=False)
    # Show Python module in stdout at DEBUG level
    fmt_string = (
        "[%(name)s] %(message)s"
        if loglevel == logging.DEBUG
        else "%(message)s"
    )
    formatter = logging.Formatter(fmt=fmt_string, datefmt="[%X]")
    rich_handler.setFormatter(formatter)
    for logger_name in loggers:
        logging.getLogger(logger_name).addHandler(rich_handler)
    # Add FileHandler if file is provided
    if file:
        file_handler = logging.FileHandler(file)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        for logger_name in loggers:
            logging.getLogger(logger_name).addHandler(file_handler)
        # If level is DEBUG and file is provided, do not send DEBUG level to stdout
        if loglevel == logging.DEBUG:
            rich_handler.setLevel(logging.INFO)

def _init_nornir(ctx: click.Context, param, value: Path) -> nornir.core.Nornir:
    try:
        return nornir.InitNornir(config_file=str(value), core={"raise_on_error": False})
    except Exception as exc:
        ctx.fail(f"Unable to initialize Nornir with config file '{value}': {str(exc)}")


def _read_otg_config(ctx: click.Context, param, value: Path) -> snappi.Config:
    try:
        config = ctx.obj["snappi_api"].config()
        with value.open(mode="r", encoding="UTF-8") as fd:
            config.deserialize(fd.read())
        logger.debug(f"OTG Configuration: {config}")
        return config
    except Exception as exc:
        ctx.fail(f"Unable to read OTG Configuration from file '{value}': {str(exc)}")

@click.group()
@click.option(
    "-n",
    "--nornir",
    "nornir",
    default="nornir.yaml",
    type=click.Path(exists=True, readable=True, dir_okay=False, path_type=Path),
    callback=_init_nornir,
    show_default=True,
    show_envvar=True,
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
        arista_lab.config.delete_backups(obj["nornir"])
    else:
        arista_lab.config.create_backups(obj["nornir"])


@cli.command(help="Restore configuration backups from flash")
@click.pass_obj
def restore(obj: dict) -> None:
    arista_lab.config.restore_backups(obj["nornir"])

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
    arista_lab.config.save(obj["nornir"], folder)

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
    arista_lab.config.create_backups(obj["nornir"])
    arista_lab.config.load(obj["nornir"], folder, replace=replace)

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
    arista_lab.config.create_backups(obj["nornir"])
    arista_lab.config.apply_templates(
        obj["nornir"], folder, replace=replace, groups=groups
    )

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
    arista_lab.config.create_backups(obj["nornir"])
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
    arista_lab.config.create_backups(obj["nornir"].filter(F(groups__contains=group)))
    arista_lab.config.peering.configure(obj["nornir"], group, backbone)

@cli.group(help="Control traffic generator")
@click.option(
    "--otg-api",
    "otg_api",
    type=str,
    required=True,
    show_envvar=True,
    help="Open Traffic Generator server",
)
@click.option(
    "--extension",
    "snappi_extension",
    type=click.Choice(["ixnetwork"]),
    show_envvar=True,
    help="Snappi Extension to use. Supported extension is 'ixnetwork'.",
)
@click.pass_context
def traffic(
    ctx: click.Context, otg_api: str, snappi_extension: Literal["ixnetwork"] | None,
) -> None:
    try:
        ctx.obj["snappi_api"] = snappi.api(
                location=otg_api,
                ext=snappi_extension,
            )
    except Exception as e:
        logger.error(e)
        ctx.exit(1)
    if snappi_extension == "ixnetwork" and arista_lab.traffic.snappi_ixnetwork_session_file.exists():
        with arista_lab.traffic.snappi_ixnetwork_session_file.open(mode="rb") as fd:
            ctx.obj["snappi_api"]._config = pickle.load(fd)

@traffic.command(help="Configure traffic generator")
@click.argument(
    "config",
    default="otg.yaml",
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    callback=_read_otg_config,
)
@click.pass_obj
def configure(
    obj: dict,
    config: snappi.Config,
) -> None:
    arista_lab.traffic.configure(api=obj["snappi_api"], config=config)

@traffic.command(help="Start the flows on the traffic generator")
@click.pass_obj
def start(
    obj: dict,
) -> None:
    arista_lab.traffic.start(api=obj["snappi_api"])

@traffic.command(help="Stop the flows on the traffic generator")
@click.pass_obj
def stop(
    obj: dict,
) -> None:
    arista_lab.traffic.stop(api=obj["snappi_api"])

@traffic.command(help="Get the flow statistics from the traffic generatorr")
@click.pass_obj
def stats(
    obj: dict,
) -> None:
    arista_lab.traffic.stats(api=obj["snappi_api"])

def main() -> None:
    try:
        sys.exit(cli(auto_envvar_prefix="LAB"))
    except Exception:
        console.print_exception()
        sys.exit(1)

if __name__ == '__main__':
    main()
