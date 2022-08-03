import os, shutil, pathlib, nornir

from nornir.core.task import Task, Result
from rich.progress import Progress

from nornir_napalm.plugins.tasks import napalm_configure
from ceos_lab.config import templates

STOP_TERMINATTR = """
daemon TerminAttr
   shutdown
!
"""
START_TERMINATTR = """
daemon TerminAttr
   no shutdown
!
"""

def onboard(nornir: nornir.core.Nornir, topology: dict, token: pathlib.Path) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Onboard to CloudVision", total=len(nornir.inventory.hosts))
        def _onboard_device_task(task: Task) -> Result:
            device_path = os.path.join(f"clab-{topology['name']}", str(task.host), 'flash', 'cv-onboarding-token')
            bar.console.log(f"Copying {token} to {device_path}")
            shutil.copyfile(token, device_path)
            task.run(task=templates, folder='onboard', bar=bar)
            task.run(task=napalm_configure, dry_run=False, configuration=STOP_TERMINATTR)
            task.run(task=napalm_configure, dry_run=False, configuration=START_TERMINATTR)
            bar.console.log(f"{task.host}: TerminAttr restarted.")
            bar.update(task_id, advance=1)
            return Result(
                host=task.host
            )
        return nornir.run(task=_onboard_device_task)
