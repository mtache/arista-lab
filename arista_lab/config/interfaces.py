from pathlib import Path
from importlib.resources import files
from arista_lab import templates
from yaml import safe_load
import ipaddress

from typing import Any
import nornir
from nornir.core.task import Task
from rich.progress import Progress
from arista_lab.console import _print_failed_tasks

from nornir_jinja2.plugins.tasks import template_file  # type: ignore[import-untyped]

from . import _safe_push

def configure(nornir: nornir.core.Nornir, file: Path) -> None:
    DESCRIPTION_KEY = "description"
    IPV4_KEY = "ipv4"
    IPV4_SUBNET_KEY = "ipv4_subnet"
    IPV6_KEY = "ipv6"
    IPV6_SUBNET_KEY = "ipv6_subnet"
    ISIS_KEY = "isis"

    def _parse_links(file: Path):
        interfaces: dict[str, Any] = {}
        with file.open(mode="r", encoding="UTF-8") as f:
            links = safe_load(f)["links"]
            for link in links:
                if len(link["endpoints"]) != 2:
                    raise Exception(
                        f"Cannot parse '{file}': entry with 'endpoints' key must have a value in the format '['device1:etN', 'device2:etN']'"
                    )
                # for device_id, neighbor_id in (range(2), range(1,-1,-1)):
                device = link["endpoints"][0].split(":")[0]
                neighbor = link["endpoints"][1].split(":")[0]
                interface = link["endpoints"][0].split(":")[1]
                neighbor_interface = link["endpoints"][1].split(":")[1]
                if device not in interfaces:
                    interfaces[device] = {}
                if neighbor not in interfaces:
                    interfaces[neighbor] = {}
                interfaces[device][interface] = {
                    DESCRIPTION_KEY: f"to {neighbor} {neighbor_interface}"
                }
                interfaces[neighbor][neighbor_interface] = {
                    DESCRIPTION_KEY: f"to {device} {interface}"
                }
                if ISIS_KEY in link:
                    interfaces[device][interface].update({ISIS_KEY: link[ISIS_KEY]})
                    interfaces[neighbor][neighbor_interface].update(
                        {ISIS_KEY: link[ISIS_KEY]}
                    )
                if IPV4_SUBNET_KEY in link:
                    network = ipaddress.ip_network(link[IPV4_SUBNET_KEY])
                    if network.prefixlen != 31:
                        raise Exception(f"Subnet {network} is not a /31 subnet")
                    interfaces[device][interface].update(
                        {IPV4_KEY: f"{network[0]}/{network.prefixlen}"}
                    )
                    interfaces[neighbor][neighbor_interface].update(
                        {IPV4_KEY: f"{network[1]}/{network.prefixlen}"}
                    )
                if IPV6_SUBNET_KEY in link:
                    network = ipaddress.ip_network(link[IPV6_SUBNET_KEY])
                    if network.prefixlen != 127:
                        raise Exception(f"Subnet {network} is not a /127 subnet")
                    interfaces[device][interface].update(
                        {IPV6_KEY: f"{network[0]}/{network.prefixlen}"}
                    )
                    interfaces[neighbor][neighbor_interface].update(
                        {IPV6_KEY: f"{network[1]}/{network.prefixlen}"}
                    )
        return interfaces

    links = _parse_links(file)
    with Progress() as bar:
        task_id = bar.add_task(
            "Configure point-to-point interfaces", total=len(nornir.inventory.hosts)
        )

        def configure_interfaces(task: Task):
            for interface, params in links[task.host.name].items():
                p = files(templates) / "interfaces"
                output = task.run(
                    task=template_file,
                    template="point-to-point.j2",
                    path=p,
                    interface={"name": interface, **params},
                )
                _safe_push(task, bar, config=output.result, title=f"Interface {interface} ({'IPv4' if IPV4_KEY in params else ''} {'IPv6' if IPV6_KEY in params else ''} {'ISIS' if ISIS_KEY in params else ''}): {params[DESCRIPTION_KEY]}")
                bar.update(task_id, advance=1)

        results = nornir.run(task=configure_interfaces)
        if results.failed:
            _print_failed_tasks(bar, results)
