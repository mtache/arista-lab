import nornir

from nornir.core.task import Task, Result, AggregatedResult
from nornir.core.inventory import Host
from typing import List
from rich.progress import Progress, TaskID
import docker  #type: ignore[import-untyped]

def stop(nornir: nornir.core.Nornir, topology: dict) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Stopping lab containers", total=len(nornir.inventory.hosts))
        def _stop(task: Task):
            client = docker.from_env()
            client.containers.get(f"clab-{topology['name']}-{task.host.name}").stop()
            bar.console.log(f"{task.host}: Stopped")
            bar.update(task_id, advance=1)
        return nornir.run(task=_stop)

def start(nornir: nornir.core.Nornir, topology: dict) -> Result:
    with Progress() as bar:
        task_id = bar.add_task("Starting lab containers", total=len(nornir.inventory.hosts))
        def _start(task: Task):
            client = docker.from_env()
            client.containers.get(f"clab-{topology['name']}-{task.host.name}").start()
            bar.console.log(f"{task.host}: Started")
            bar.update(task_id, advance=1)
        return nornir.run(task=_start)

def restart(task: Task, topology: dict, bar: Progress, task_id: TaskID):
    client = docker.from_env()
    client.containers.get(f"clab-{topology['name']}-{task.host.name}").restart()
    bar.console.log(f"{task.host}: Restarted")
    bar.update(task_id, advance=1)

def host_exists(host: Host, topology: dict) -> bool:
    client = docker.from_env()
    for container in client.containers.list():
        if container.name == f"clab-{topology['name']}-{host.name}":
            return True
    return False

def restart_pending(nornir: nornir.core.Nornir, topology: dict, results: List[AggregatedResult]) -> Result:
    pending_nodes = set()
    for agg_res in results:
        for host in agg_res:
            if agg_res[host].changed:
                pending_nodes.add(host)
    with Progress() as bar:
        task_id = bar.add_task("Restart nodes", total=len(pending_nodes))
        nodes = nornir.filter(filter_func=lambda h: h.name in pending_nodes)
        return nodes.run(task=restart, topology=topology, bar=bar, task_id=task_id)

