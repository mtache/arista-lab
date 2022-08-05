import os, shutil, pathlib, nornir

from nornir.core.task import Task, Result
from rich.progress import Progress
from arista_lab import templates
from importlib.resources import path
from nornir_napalm.plugins.tasks import napalm_configure
from arista_lab.config import apply_templates

CLEAN_TERMINATTR = "no daemon TerminAttr"

def onboard(nornir: nornir.core.Nornir, topology: dict, token: pathlib.Path) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Onboard to CloudVision", total=len(nornir.inventory.hosts))
        def onboard_device(task: Task):
            device_path = os.path.join(f"clab-{topology['name']}", str(task.host), 'flash', 'cv-onboarding-token')
            bar.console.log(f"Copying {token} to {device_path}")
            shutil.copyfile(token, device_path)
            task.run(task=napalm_configure, dry_run=False, configuration=CLEAN_TERMINATTR)
            with path(templates, 'onboard') as p:
                task.run(task=apply_templates, folder=p, bar=bar)
            bar.update(task_id, advance=1)
        return nornir.run(task=onboard_device)
