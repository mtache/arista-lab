#!/usr/bin/env python3

import nornir, click, yaml, sys, os
from pathlib import Path
from rich.console import Console
from nornir.core.task import Result
from nornir_utils.plugins.functions import print_result

from ceos_lab import config, cloudvision

def _init_nornir(ctx: click.Context, param, value) -> nornir.core.Nornir:
    try:
        return nornir.InitNornir(config_file=value)
    except Exception as exc:
        ctx.fail(f"Unable to initialize Nornir with config file '{value}': {str(exc)}")

def _parse_topology(ctx: click.Context, param, value) -> dict:
    try:
        t = yaml.safe_load(value)
        t.update({'_topology_path': value.name})
        return t
    except Exception as exc:
        ctx.fail(f"Unable to read Containerlab topology file '{value.name}': {str(exc)}")

@click.group()
@click.option('-n', '--nornir', 'nornir', default='nornir.yaml', type=click.Path(exists=True), callback=_init_nornir, help='Nornir configuration in YAML format.')
@click.option('-t', '--topology', 'topology', default='topology.yaml', type=click.File('r'), callback=_parse_topology, help='Containerlab topology file.')
@click.pass_context
def cli(ctx, nornir: nornir.core.Nornir, topology: dict):
    ctx.ensure_object(dict)
    ctx.obj['nornir'] = nornir
    ctx.obj['topology'] = topology

@cli.result_callback()
def print_failed_results(result, nornir, topology):
    def _print(result):
        if isinstance(result, Result):
            print_result(result, vars=['exception'])
            return
        for r in result:
            if r.failed:
                _print(r)
    if result.failed:
        for device in result.failed_hosts:
            _print(result[device])

# Backup on flash

@cli.command(help='Create or delete device configuration backups to flash')
@click.pass_obj
@click.option('--delete/--no-delete', default=False, help='Delete the backup on the device flash')
def backup(obj: dict, delete: bool):
    if delete:
        return config.delete_backups(obj['nornir'])
    else:
        return config.create_backups(obj['nornir'])

@cli.command(help='Restore configuration backups from flash')
@click.pass_obj
def restore(obj: dict): 
    return config.restore_backups(obj['nornir'])

# Backup locally

@cli.command(help='Save lab configuration to a folder')
@click.pass_obj
@click.option('--folder', 'folder', type=click.Path(writable=True, path_type=Path), required=True, help='Lab configuration folder')
def save(obj: dict, folder: Path):
    return config.save(obj['nornir'], folder, obj['topology'])

@cli.command(help='Load lab configuration from a folder')
@click.pass_obj
@click.option('--folder', 'folder', type=click.Path(writable=True, path_type=Path), required=True, help='Lab configuration folder')
def load(obj: dict, folder: Path):
    config.create_backups(obj['nornir'])
    return config.load(obj['nornir'], folder, obj['topology'])

# CloudVision

@cli.command(help='Onboard lab to CloudVision')
@click.option('--token', 'token', type=click.Path(exists=True, readable=True, path_type=Path), help='CloudVision onboarding token')
@click.pass_obj
def onboard(obj: dict, token: Path):
    config.create_backups(obj['nornir'])
    return cloudvision.onboard(obj['nornir'], obj['topology'], token)

if __name__ == '__main__':
    try:
        cli()
        sys.exit(0)
    except Exception:
        Console().print_exception(suppress=os.environ)
        sys.exit(1)