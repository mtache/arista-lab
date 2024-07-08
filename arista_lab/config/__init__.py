from pathlib import Path
from os import walk

import nornir
from nornir.core.task import Task
from rich.progress import Progress
from arista_lab.console import _print_failed_tasks

from nornir_napalm.plugins.tasks import napalm_cli, napalm_configure, napalm_get, napalm_confirm_commit  # type: ignore[import-untyped]
from nornir_jinja2.plugins.tasks import template_file  # type: ignore[import-untyped]

#############
# Templates #
#############


def apply_templates(
    nornir: nornir.core.Nornir,
    folder: Path,
    replace: bool = False,
    groups: bool = False,
) -> None:
    if not folder.exists():
        raise Exception(f"Could not find template folder {folder}")
    templates = []
    for dirpath, _, filenames in walk(folder):
        group = None
        if groups and len(dirpath.split("/")) > 1:
            # This refers to a group
            group = dirpath.split("/")[1]
        for file in filenames:
            if file.endswith(".j2"):
                templates.append((dirpath, file, group))
    with Progress() as bar:
        task_id = bar.add_task(
            "Apply configuration templates to devices",
            total=len(nornir.inventory.hosts) * len(templates),
        )

        def apply_templates(task: Task):
            for t in templates:
                if groups and not (
                    (group := t[2]) is None or group in task.host.groups
                ):
                    # Only apply templates specific to a group or templates with no group
                    bar.update(task_id, advance=1)
                    continue
                output = task.run(
                    task=template_file,
                    template=(template := t[1]),
                    path=t[0],
                    hosts=nornir.inventory.hosts,
                    groups=nornir.inventory.groups,
                )
                r = task.run(
                    task=napalm_configure,
                    dry_run=False,
                    replace=replace,
                    configuration=output.result,
                    revert_in=30,
                )
                if r.changed:
                    bar.console.log(f"{task.host}: {template}\n{r.diff}")
                r = task.run(task=napalm_confirm_commit)
                bar.console.log(f"{task.host}: {template}: {r.result}")
                bar.update(task_id, advance=1)


        results = nornir.run(task=apply_templates)
        if results.failed:
            _print_failed_tasks(bar, results)


###################
# Backup to flash #
###################


DIR_FLASH_CMD = "dir flash:"
BACKUP_FILENAME = "rollback-config"


def create_backups(nornir: nornir.core.Nornir) -> None:
    with Progress() as bar:
        task_id = bar.add_task(
            "Backup configuration to flash", total=len(nornir.inventory.hosts)
        )

        def create_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    bar.console.log(f"{task.host}: Backup already present.")
                    bar.update(task_id, advance=1)
                    return
            task.run(
                task=napalm_cli,
                commands=[f"copy running-config flash:{BACKUP_FILENAME}"],
            )
            bar.console.log(f"{task.host}: Backup created.")
            bar.update(task_id, advance=1)

        results = nornir.run(task=create_backup)
        if results.failed:
            _print_failed_tasks(bar, results)


def restore_backups(nornir: nornir.core.Nornir) -> None:
    with Progress() as bar:
        task_id = bar.add_task(
            "Restore backup configuration from flash", total=len(nornir.inventory.hosts)
        )

        def restore_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    task.run(
                        task=napalm_cli,
                        commands=[f"configure replace flash:{BACKUP_FILENAME}"],
                    )
                    # Intentionally not copying running-config to startup-config here.
                    # If there is a napalm_configure following a restore, configuration will be saved.
                    # This behaviour is acceptable, user can retrieve previous configuration in startup-config
                    # in case of mis-restoring the configuration.
                    bar.console.log(f"{task.host}: Backup restored.")
                    bar.update(task_id, advance=1)
                    return
            raise Exception(f"{task.host}: Backup not found.")

        results = nornir.run(task=restore_backup)
        if results.failed:
            _print_failed_tasks(bar, results)


def delete_backups(nornir: nornir.core.Nornir) -> None:
    with Progress() as bar:
        task_id = bar.add_task(
            "Delete backup on flash", total=len(nornir.inventory.hosts)
        )

        def delete_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    task.run(
                        task=napalm_cli, commands=[f"delete flash:{BACKUP_FILENAME}"]
                    )
                    bar.console.log(f"{task.host}: Backup deleted.")
                    bar.update(task_id, advance=1)
                    return
            bar.console.log(f"{task.host}: Backup not found.")
            bar.update(task_id, advance=1)

        results = nornir.run(task=delete_backup)
        if results.failed:
            _print_failed_tasks(bar, results)


###############################
# Save and load configuration #
###############################


def save(nornir: nornir.core.Nornir, folder: Path) -> None:
    with Progress() as bar:
        task_id = bar.add_task(
            "Save lab configuration", total=len(nornir.inventory.hosts)
        )

        def save_config(task: Task):
            task.run(task=napalm_cli, commands=["copy running-config startup-config"])
            r = task.run(task=napalm_get, getters=["config"])
            config = folder / f"{task.host}.cfg"
            folder.mkdir(parents=True, exist_ok=True)
            with open(config, "w") as file:
                file.write(r[0].result["config"]["running"])
            bar.console.log(f"{task.host}: Configuration saved to {config}")
            bar.update(task_id, advance=1)

        results = nornir.run(task=save_config)
        if results.failed:
            _print_failed_tasks(bar, results)


def load(nornir: nornir.core.Nornir, folder: Path, replace: bool = False) -> None:
    with Progress() as bar:
        task_id = bar.add_task(
            "Load lab configuration", total=len(nornir.inventory.hosts)
        )

        def load_config(task: Task):
            config = folder / f"{task.host}.cfg"
            if not config.exists():
                raise Exception(
                    f"Configuration of {task.host} not found in folder {folder}"
                )
            output = task.run(
                task=template_file, template=f"{task.host}.cfg", path=folder
            )
            task.run(
                task=napalm_configure,
                dry_run=False,
                replace=replace,
                configuration=output.result,
                revert_in=30,
            )
            r = task.run(task=napalm_confirm_commit)
            bar.console.log(f"{task.host}: {r.result}")
            bar.update(task_id, advance=1)

        results = nornir.run(task=load_config)
        if results.failed:
            _print_failed_tasks(bar, results)
