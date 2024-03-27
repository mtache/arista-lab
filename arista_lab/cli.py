import nornir
import click
import yaml
import sys

from rich.console import Console
from pathlib import Path
from nornir.core.filter import F

from arista_lab import config, ceos, docker

console = Console()


def _init_nornir(ctx: click.Context, param, value) -> nornir.core.Nornir:
    try:
        return nornir.InitNornir(config_file=value, core={"raise_on_error": False})
    except Exception as exc:
        ctx.fail(f"Unable to initialize Nornir with config file '{value}': {str(exc)}")


def _parse_topology(ctx: click.Context, param, value) -> dict:
    try:
        t = yaml.safe_load(value)
        t.update({"_topology_path": value.name})
        return t
    except Exception as exc:
        ctx.fail(
            f"Unable to read Containerlab topology file '{value.name}': {str(exc)}"
        )


@click.group()
@click.option(
    "-n",
    "--nornir",
    "nornir",
    default="nornir.yaml",
    type=click.Path(exists=True),
    callback=_init_nornir,
    help="Nornir configuration in YAML format.",
)
@click.pass_context
def cli(ctx, nornir: nornir.core.Nornir) -> None:
    ctx.ensure_object(dict)
    ctx.obj["nornir"] = nornir


# Backup on flash


@cli.command(help="Create or delete device configuration backups to flash")
@click.pass_obj
@click.option(
    "--delete/--no-delete", default=False, help="Delete the backup on the device flash"
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


# Backup locally


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
def load(obj: dict, folder: Path) -> None:
    config.create_backups(obj["nornir"])
    config.load(obj["nornir"], folder)


# Containerlab


@cli.command(help="Start containers")
@click.option(
    "-t",
    "--topology",
    "topology",
    default="topology.clab.yml",
    type=click.File("r"),
    callback=_parse_topology,
    help="Containerlab topology file.",
)
@click.pass_obj
def start(obj: dict, topology: dict) -> None:
    docker.start(obj["nornir"], topology)


@cli.command(help="Stop containers")
@click.option(
    "-t",
    "--topology",
    "topology",
    default="topology.clab.yml",
    type=click.File("r"),
    callback=_parse_topology,
    help="Containerlab topology file.",
)
@click.pass_obj
def stop(obj: dict, topology: dict) -> None:
    docker.stop(obj["nornir"], topology)


@cli.command(
    help="Configure cEOS serial number, system MAC address and copy CloudVision token to flash"
)
@click.option(
    "--token",
    "token",
    type=click.Path(exists=True, readable=True, path_type=Path),
    required=False,
    help="CloudVision onboarding token",
)
@click.pass_obj
@click.option(
    "-t",
    "--topology",
    "topology",
    default="topology.clab.yml",
    type=click.File("r"),
    callback=_parse_topology,
    help="Containerlab topology file.",
)
def init_ceos(obj: dict, topology: dict, token: Path) -> None:
    ceos.init_ceos_flash(obj["nornir"], topology, token)


# Configuration


@cli.command(
    help="Onboard to CloudVision (N.B: TerminAttr uses default VRF and CVaaS cv-staging cluster)"
)
@click.pass_obj
def onboard(obj: dict) -> None:
    config.create_backups(obj["nornir"])
    config.onboard_cloudvision(obj["nornir"])


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
    help="The template folder contains subfolders with Nornir group names",
)
def apply(obj: dict, folder: Path, groups: bool) -> None:
    config.create_backups(obj["nornir"])
    config.apply_templates(obj["nornir"], folder, groups=groups)


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
    config.configure_interfaces(obj["nornir"], links)


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
    config.configure_peering(obj["nornir"], group, backbone)


def main() -> None:
    try:
        sys.exit(cli(max_content_width=120))
    except Exception:
        console.print_exception()
        sys.exit(1)
