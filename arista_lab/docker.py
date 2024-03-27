import nornir

from arista_lab.console import _print_failed_tasks

from nornir.core.task import Task
from nornir.core.inventory import Host
from rich.progress import Progress
import docker  # type: ignore[import-untyped]


def stop(nornir: nornir.core.Nornir, topology: dict) -> None:
    with Progress() as bar:
        task_id = bar.add_task(
            "Stopping lab containers", total=len(nornir.inventory.hosts)
        )

        def _stop(task: Task):
            client = docker.from_env()
            client.containers.get(f"clab-{topology['name']}-{task.host.name}").stop()
            bar.console.log(f"{task.host}: Stopped")
            bar.update(task_id, advance=1)

        results = nornir.run(task=_stop)
        if results.failed:
            _print_failed_tasks(bar, results)


def start(nornir: nornir.core.Nornir, topology: dict) -> None:
    with Progress() as bar:
        task_id = bar.add_task(
            "Starting lab containers", total=len(nornir.inventory.hosts)
        )

        def _start(task: Task):
            client = docker.from_env()
            client.containers.get(f"clab-{topology['name']}-{task.host.name}").start()
            bar.console.log(f"{task.host}: Started")
            bar.update(task_id, advance=1)

        results = nornir.run(task=_start)
        if results.failed:
            _print_failed_tasks(bar, results)


def host_exists(host: Host, topology: dict) -> bool:
    client = docker.from_env()
    for container in client.containers.list():
        if container.name == f"clab-{topology['name']}-{host.name}":
            return True
    return False
