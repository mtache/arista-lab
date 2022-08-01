import os, shutil, pathlib, nornir
from nornir.core.task import Task, Result
from rich.progress import Progress

from .config import templates

def onboard(nornir: nornir.core.Nornir, topology: dict, token: pathlib.Path) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Onboard to CloudVision", total=len(nornir.inventory.hosts))
        def _onboard_device_task(task: Task) -> Result:
            device_path = os.path.join(f"clab-{topology['name']}", str(task.host), 'flash', 'cv-onboarding-token')
            bar.console.log(f"Copying {token} to {device_path}")
            shutil.copyfile(token, device_path)
            task.run(task=templates, folder='onboard', bar=bar)
            bar.update(task_id, advance=1)
        return nornir.run(task=_onboard_device_task)
