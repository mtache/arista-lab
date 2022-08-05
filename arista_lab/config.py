import shutil, nornir, re

from nornir.core.task import Task, Result
from rich.progress import Progress
from pathlib import Path
from arista_lab import templates
from importlib.resources import path

from os import walk
from nornir_napalm.plugins.tasks import napalm_cli, napalm_configure
from nornir_jinja2.plugins.tasks import template_file

CONFIG_CHANGED = ' New configuration applied.'
MANAGEMENT_REGEX = "interface Management[0-1]\n(.  ip address .*)?(\n   ipv6 address .*)?"

#############
# Templates #
#############

def _purge_management_config(config):
    return re.sub(MANAGEMENT_REGEX, '', config)

def apply_group_templates(task: Task, bar: Progress):
    with path(templates, '.') as p:
        for (dirpath, _, filenames) in walk(p):
            if len(dirpath.split('/')) > 1:
                # This refers to a group
                folder = dirpath.split('/')[1]
                if folder in task.host.groups:
                    for file in filenames:
                        if file.endswith('.j2'):
                            task.run(task=apply_template, path=dirpath, file=file, bar=bar)

def apply_templates(task: Task, folder: Path, bar: Progress, replace: bool = False):
    if not folder.exists():
        raise Exception(f'Could not find template folder {folder}')
    for (dirpath, _, filenames) in walk(folder):
        for file in filenames:
            if file.endswith('.j2'):
                task.run(task=apply_template, replace=replace, path=dirpath, file=file, bar=bar)

def apply_template(task: Task, path: str, file: str, bar: Progress, replace: bool = False):
    output = task.run(task=template_file, template=file, path=path)
    r = task.run(task=napalm_configure, dry_run=False, replace=replace, configuration=_purge_management_config(output.result))
    bar.console.log(f"{task.host}: {file} template configured.{CONFIG_CHANGED if r.changed else ''}")

###################
# Backup to flash #
###################

DIR_FLASH_CMD = 'dir flash:'
BACKUP_FILENAME = 'rollback-config'

def create_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Backup configuration to flash", total=len(nornir.inventory.hosts))
        def create_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    bar.console.log(f"{task.host}: Backup already present.")
                    bar.update(task_id, advance=1)
                    return
            task.run(task=napalm_cli, commands=[f'copy running-config flash:{BACKUP_FILENAME}'])
            bar.console.log(f"{task.host}: Backup created.")
            bar.update(task_id, advance=1)
        return nornir.run(task=create_backup)

def restore_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Restore backup configuration from flash", total=len(nornir.inventory.hosts))
        def restore_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    task.run(task=napalm_cli, commands=[f'configure replace flash:{BACKUP_FILENAME}'])
                    # Intentionally not copying running-config to startup-config here.
                    # If there is a napalm_configure following a restore, configuration will be saved.
                    # This behaviour is acceptable, user can retrieve previous configuration in startup-config
                    # in case of mis-restoring the configuration.
                    # task.run(task=napalm_cli, commands=[f'copy running-config startup-config'])
                    bar.console.log(f"{task.host}: Backup restored.")
                    bar.update(task_id, advance=1)
                    return
            raise Exception(f"{task.host}: Backup not found.")
        return nornir.run(task=restore_backup)

def delete_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Delete backup on flash", total=len(nornir.inventory.hosts))
        def delete_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    task.run(task=napalm_cli, commands=[f'delete flash:{BACKUP_FILENAME}'])
                    bar.console.log(f"{task.host}: Backup deleted.")
                    bar.update(task_id, advance=1)
                    return
            bar.console.log(f"{task.host}: Backup not found.")
            bar.update(task_id, advance=1)
        return nornir.run(task=delete_backup)

###############################
# Save and load configuration #
###############################

def save(nornir: nornir.core.Nornir, folder: Path, topology: dict) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Save lab configuration", total=len(nornir.inventory.hosts))
        def save_config(task: Task):
            task.run(task=napalm_cli, commands=[f'copy running-config startup-config'])
            startup = Path(f"clab-{topology['name']}") / str(task.host) / 'flash' / 'startup-config'
            config = folder / f'{task.host}.cfg'
            bar.console.log(f"Copying {startup} to {config}")
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(startup, config)
            bar.console.log(f"{task.host}: Configuration saved.")
            bar.update(task_id, advance=1)
        return nornir.run(task=save_config)

def load(nornir: nornir.core.Nornir, folder: Path) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Load lab configuration", total=len(nornir.inventory.hosts))
        def load_config(task: Task):
            config = folder / f'{task.host}.cfg'
            if not config.exists():
                raise Exception(f'Configuration of {task.host} not found in folder {folder}')            
            task.run(task=apply_template, replace=False, path=folder, file=f'{task.host}.cfg', bar=bar)
            bar.console.log(f"{task.host}: Configuration loaded.")
            bar.update(task_id, advance=1)
        return nornir.run(task=load_config)