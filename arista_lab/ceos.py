import nornir

import shutil
from nornir.core.task import Task, Result
from rich.progress import Progress
from pathlib import Path

from arista_lab import docker


def init_ceos_flash(nornir: nornir.core.Nornir, topology: dict, token: Path) -> Result:
    with Progress() as bar:

        def configure_system_mac(task: Task, device_flash: Path) -> bool:
            device_system_mac = device_flash / "system_mac_address"
            if "system_mac" not in task.host.data:
                bar.console.log(
                    f"{task.host}: System MAC address omitted in inventory. Not configuring..."
                )
                return False
            if device_system_mac.exists():
                bar.console.log(
                    f"{task.host}: System MAC address already configured. Use 'containerlab destroy --cleanup' if you want to override."
                )
                return False
            bar.console.log(f"Creating {device_system_mac}")
            with device_system_mac.open("w", encoding="utf-8") as f:
                f.write(task.host.data["system_mac"])
            bar.console.log(f"{task.host}: System MAC address configured.")
            return True

        def configure_serial_number(task: Task, device_flash: Path) -> bool:
            device_serial_number = device_flash / "ceos-config"
            if "serial_number" not in task.host.data:
                bar.console.log(
                    f"{task.host}: Serial number omitted in inventory. Not configuring..."
                )
                return False
            if device_serial_number.exists():
                bar.console.log(
                    f"{task.host}: Serial Number already configured. Use 'containerlab destroy --cleanup' if you want to override."
                )
                return False
            bar.console.log(f"Creating {device_serial_number}")
            with device_serial_number.open("w", encoding="utf-8") as f:
                f.write(f"SERIALNUMBER={task.host.data['serial_number']}")
            bar.console.log(f"{task.host}: Serial number configured.")
            return True

        def copy_cv_token(task: Task, device_flash: Path) -> bool:
            device_cv_token = device_flash / "cv-onboarding-token"
            if token is None:
                bar.console.log(
                    f"{task.host}: CloudVision token has not been provided. Not configuring..."
                )
                return False
            bar.console.log(f"Copying {token} to {device_cv_token}")
            shutil.copyfile(token, device_cv_token)
            bar.console.log(f"{task.host}: CloudVision token copied.")
            return True

        task_id = bar.add_task("Init cEOS flash", total=len(nornir.inventory.hosts))

        def init_ceos_flash(task: Task):
            device_flash = Path(f"clab-{topology['name']}") / str(task.host) / "flash"
            device_flash.mkdir(parents=True, exist_ok=True)
            # CloudVision Token
            changed = copy_cv_token(task, device_flash)
            if docker.host_exists(task.host, topology):
                bar.console.log(
                    f"{task.host}: Container has already been created. Cannot init cEOS flash."
                )
                return Result(host=task.host, changed=False)
            # System MAC
            changed = configure_system_mac(task, device_flash) or changed
            # Serial Number
            changed = configure_serial_number(task, device_flash) or changed
            bar.update(task_id, advance=1)
            return Result(host=task.host, changed=changed)

        return nornir.run(task=init_ceos_flash)
