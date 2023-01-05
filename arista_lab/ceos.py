import nornir

from nornir.core.task import Task, Result
from rich.progress import Progress
from pathlib import Path

from arista_lab import docker

def configure_system_mac(nornir: nornir.core.Nornir, topology: dict) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Configure System MAC address", total=len(nornir.inventory.hosts))
        def configure_system_mac(task: Task):
            if 'system_mac' not in task.host.data:
                bar.console.log(f"{task.host}: System MAC address omitted in inventory. Not configuring...")
                bar.update(task_id, advance=1)
                return Result(host=task.host, changed=False)
            device_flash = Path(f"clab-{topology['name']}") / str(task.host) / 'flash'
            device_flash.mkdir(parents=True, exist_ok=True)
            device_system_mac = device_flash / 'system_mac_address'
            if device_system_mac.exists():
                bar.console.log(f"{task.host}: System MAC address already configured. Cannot override the system MAC address.")
                return Result(host=task.host, failed=True)
            bar.console.log(f"Creating {device_system_mac}")
            with device_system_mac.open("w", encoding ="utf-8") as f:
                f.write(task.host.data['system_mac'])
            bar.console.log(f"{task.host}: System MAC address configured.")
            bar.update(task_id, advance=1)
            return Result(host=task.host, changed=True)
        return nornir.run(task=configure_system_mac)

def configure_serial_number(nornir: nornir.core.Nornir, topology: dict) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Configure serial number", total=len(nornir.inventory.hosts))
        def configure_serial_number(task: Task):
            if 'serial_number' not in task.host.data:
                bar.console.log(f"{task.host}: Serial number omitted in inventory. Not configuring...")
                bar.update(task_id, advance=1)
                return Result(host=task.host, changed=False)
            if docker.host_exists(task.host, topology):
                bar.console.log(f"{task.host}: Container has already been created. Cannot override the serial number.")
                return Result(host=task.host, failed=True)
            device_flash = Path(f"clab-{topology['name']}") / str(task.host) / 'flash'
            device_flash.mkdir(parents=True, exist_ok=True)
            device_serial_number = device_flash / 'ceos-config'
            bar.console.log(f"Creating {device_serial_number}")
            with device_serial_number.open("w", encoding ="utf-8") as f:
                f.write(f"SERIALNUMBER={task.host.data['serial_number']}")
            bar.console.log(f"{task.host}: Serial number configured.")
            bar.update(task_id, advance=1)
            return Result(host=task.host, changed=True)
        return nornir.run(task=configure_serial_number)
