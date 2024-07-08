from importlib.resources import files
from arista_lab import templates
from datetime import datetime, timedelta
import ipaddress

import requests
import nornir
from nornir.core.task import Task
from nornir.core.filter import F
from rich.progress import Progress
from arista_lab.console import _print_failed_tasks

from nornir_napalm.plugins.tasks import napalm_configure  # type: ignore[import-untyped]
from nornir_jinja2.plugins.tasks import template_file  # type: ignore[import-untyped]

from arista_lab.config import CONFIG_CHANGED


def configure(nornir: nornir.core.Nornir, group: str, neighbor_group: str) -> None:
    def _build_vars(asn: int):
        start_time = datetime.now() - timedelta(days=10)
        url = f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}&starttime={start_time.strftime('%Y-%m-%dT%H:%M')}"
        r = requests.get(url)
        if r.ok:
            prefixes = []
            for prefix in r.json()["data"]["prefixes"]:
                prefixes.append(prefix["prefix"])
        else:
            raise Exception(f"Could not get announced prefixes for AS{asn}")
        networks = []
        for network in [ipaddress.ip_network(p) for p in prefixes]:
            if not any(
                (network != n and network.overlaps(n))
                for n in [ipaddress.ip_network(p) for p in prefixes]
            ):
                networks.append(network)

        hosts = []
        hosts_ipv6 = []
        prefixes = []
        prefixes_ipv6 = []
        for network in networks:
            if network.version == 4:
                hosts.append(f"{next(network.hosts())}/{network.prefixlen}")
                prefixes.append(str(network))
            elif network.version == 6:
                hosts_ipv6.append(f"{next(network.hosts())}/{network.prefixlen}")
                prefixes_ipv6.append(str(network))

        return {
            "hosts": hosts,
            "hosts_ipv6": hosts_ipv6,
            "prefixes": prefixes,
            "prefixes_ipv6": prefixes_ipv6,
        }

    with Progress() as bar:
        task_id = bar.add_task(
            "Configure peering devices",
            total=len(nornir.inventory.children_of_group(group)),
        )

        def configure_peering(task: Task):
            MAX_LOOPBACKS = 2100
            vars = _build_vars(task.host.data["asn"])
            bar.console.log(
                f"{task.host}: Configuring {len(vars['prefixes'])} IPv4 prefixes for ISP {task.host.data['isp']}"
            )
            # bar.console.log(f"{task.host}: {vars['prefixes']}")
            bar.console.log(
                f"{task.host}: Configuring {len(vars['prefixes_ipv6'])} IPv6 prefixes for ISP {task.host.data['isp']}"
            )
            # bar.console.log(f"{task.host}: {vars['prefixes_ipv6']}")
            vars.update(
                {
                    "name": task.host.data["isp"],
                    "asn": task.host.data["asn"],
                    "description": task.host.data["description"],
                    "as_path_length": task.host.data["as_path_length"],
                    "max_loopback": MAX_LOOPBACKS,
                    "neighbor_name": task.nornir.inventory.groups[neighbor_group].data[
                        "network_name"
                    ],
                    "neighbor_ipv4": task.host.data["neighbor_ipv4"],
                    "neighbor_ipv6": task.host.data["neighbor_ipv6"],
                    "neighbor_as": task.nornir.inventory.groups[neighbor_group].data[
                        "asn"
                    ],
                }
            )

            p = files(templates) / "peering"
            output = task.run(task=template_file, template="isp.j2", path=p, vars=vars)
            r = task.run(
                task=napalm_configure,
                dry_run=False,
                configuration=output.result,
                revert_in=5,
            )
            bar.console.log(
                f"{task.host}: Peering with {task.nornir.inventory.groups[neighbor_group].data['network_name']} configured.{CONFIG_CHANGED if r.changed else ''}"
            )
            bar.update(task_id, advance=1)

        results = nornir.filter(F(groups__contains=group)).run(task=configure_peering)
        if results.failed:
            _print_failed_tasks(bar, results)
