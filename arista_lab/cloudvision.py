import os, shutil, pathlib, nornir

from nornir.core.task import Task, Result
from rich.progress import Progress
from arista_lab import templates
from importlib.resources import path
from nornir_napalm.plugins.tasks import napalm_configure
from arista_lab import config

CLEAN_TERMINATTR = "no daemon TerminAttr"

def onboard(nornir: nornir.core.Nornir, topology: dict, token: pathlib.Path) -> Result:
    r = []
    with Progress() as bar:
        task_id = bar.add_task("Prepare devices to CloudVision onboarding", total=len(nornir.inventory.hosts))
        def onboard_device(task: Task):
            device_path = os.path.join(f"clab-{topology['name']}", str(task.host), 'flash', 'cv-onboarding-token')
            bar.console.log(f"Copying {token} to {device_path}")
            # TODO: check if device folder exists and raise error if not
            shutil.copyfile(token, device_path)
            task.run(task=napalm_configure, dry_run=False, configuration=CLEAN_TERMINATTR)
            bar.update(task_id, advance=1)
        r.append(nornir.run(task=onboard_device))
    with path(templates, 'onboard') as p:
        r.append(config.apply_templates(nornir=nornir, folder=p))
    return r
