import shutil, nornir
from pathlib import Path
from os import walk
from nornir.core.task import Task, Result
from nornir_napalm.plugins.tasks import napalm_cli, napalm_configure
from nornir_jinja2.plugins.tasks import template_file
from rich.progress import Progress

CONFIG_CHANGED = ' New configuration applied.'

#############
# Templates #
#############

def groups(task: Task, bar: Progress) -> Result:
    for (dirpath, _, filenames) in walk('templates'):
        group = None
        if len(dirpath.split('/')) > 1:
            # This refers to a group
            folder = dirpath.split('/')[1]
            group = folder
        if group in task.host.groups:
            for file in filenames:
                if file.endswith('.j2'):
                    task.run(task=template, path=dirpath, file=file, bar=bar)
    return Result(
        host=task.host
    )

def templates(task: Task, folder: str, bar: Progress) -> Result:
    for (dirpath, _, filenames) in walk(f'templates/{folder}'):
        for file in filenames:
            if file.endswith('.j2'):
                task.run(task=template, path=dirpath, file=file, bar=bar)
    return Result(
        host=task.host
    )

def template(task: Task, path: str, file: str, bar: Progress) -> Result:
    output = task.run(task=template_file, template=file, path=path)
    r = task.run(task=napalm_configure, dry_run=False, configuration=output.result)
    bar.console.log(f"{task.host}: {file} template configured.{CONFIG_CHANGED if r.changed else ''}")
    return Result(
        host=task.host
    )

###################
# Backup to flash #
###################

DIR_FLASH_CMD = 'dir flash:'
BACKUP_FILENAME = 'rollback-config'

def create_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Backup configuration to flash", total=len(nornir.inventory.hosts))
        def _create_backup_task(task: Task) -> Result:
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    bar.console.log(f"{task.host}: Backup already present.")
                    bar.update(task_id, advance=1)
                    return Result(
                        host=task.host
                    )
            task.run(task=napalm_cli, commands=[f'copy running-config flash:{BACKUP_FILENAME}'])
            bar.console.log(f"{task.host}: Backup created.")
            bar.update(task_id, advance=1)
            return Result(
                    host=task.host
                )
        return nornir.run(task=_create_backup_task)

def restore_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Restore backup configuration from flash", total=len(nornir.inventory.hosts))
        def _restore_backup_task(task: Task) -> Result:
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
                    return Result(
                        host=task.host
                    )
            raise Exception(f"{task.host}: Backup not found.")
        return nornir.run(task=_restore_backup_task)

def delete_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Delete backup on flash", total=len(nornir.inventory.hosts))
        def _delete_backup_task(task: Task) -> Result:
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    task.run(task=napalm_cli, commands=[f'delete flash:{BACKUP_FILENAME}'])
                    bar.console.log(f"{task.host}: Backup deleted.")
                    bar.update(task_id, advance=1)
                    return Result(
                        host=task.host
                    )
            bar.console.log(f"{task.host}: Backup not found.")
            bar.update(task_id, advance=1)
            return Result(
                    host=task.host
                )
        return nornir.run(task=_delete_backup_task)

###############################
# Save and load configuration #
###############################

def save(nornir: nornir.core.Nornir, folder: Path, topology: dict) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Save lab configuration", total=len(nornir.inventory.hosts))
        def _save_config_task(task: Task) -> Result:
            task.run(task=napalm_cli, commands=[f'copy running-config startup-config'])
            startup = Path(f"clab-{topology['name']}") / str(task.host) / 'flash' / 'startup-config'
            config = folder / f'{task.host}.cfg'
            bar.console.log(f"Copying {startup} to {config}")
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(startup, config)
            bar.console.log(f"{task.host}: Configuration saved.")
            bar.update(task_id, advance=1)
            return Result(
                host=task.host
            )
        return nornir.run(task=_save_config_task)


def load(nornir: nornir.core.Nornir, folder: Path, topology: dict) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Load lab configuration", total=len(nornir.inventory.hosts))
        def _load_config_task(task: Task) -> Result:
            startup = Path(f"clab-{topology['name']}") / str(task.host) / 'flash' / 'startup-config'
            config = folder / f'{task.host}.cfg'
            if not config.exists():
                raise Exception(f'Configuration of {task.host} not found in folder {folder}')
            bar.console.log(f"Copying {config} to {startup}")
            shutil.copyfile(config, startup)
            task.run(task=napalm_cli, commands=[f'copy startup-config running-config'])
            bar.console.log(f"{task.host}: Configuration loaded.")
            bar.update(task_id, advance=1)
            return Result(
                host=task.host
            )
        return nornir.run(task=_load_config_task)