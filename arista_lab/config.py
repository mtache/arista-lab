from pathlib import Path
import re
from os import walk
from importlib.resources import files, as_file
from arista_lab import templates
from datetime import datetime, timedelta
from yaml import safe_load
import ipaddress

from typing import Any
import requests
import nornir
from nornir.core.task import Task, Result
from nornir.core.filter import F
from rich.progress import Progress

from nornir_napalm.plugins.tasks import napalm_cli, napalm_configure, napalm_get  # type: ignore[import-untyped]
from nornir_jinja2.plugins.tasks import template_file  # type: ignore[import-untyped]

CONFIG_CHANGED = " New configuration applied."
MANAGEMENT_REGEX = (
    "interface Management[0-1]\n(.  ip address .*)?(\n   ipv6 address .*)?"
)

#############
# Templates #
#############


def _purge_management_config(config):
    return re.sub(MANAGEMENT_REGEX, "", config)


def apply_templates(
    nornir: nornir.core.Nornir,
    folder: Path,
    replace: bool = False,
    groups: bool = False,
) -> Result:
    if not folder.exists():
        raise Exception(f"Could not find template folder {folder}")
    templates = []
    for dirpath, _, filenames in walk(folder):
        group = None
        if groups and len(dirpath.split("/")) > 1:
            # This refers to a group
            group = dirpath.split("/")[1]
        for file in filenames:
            if file.endswith(".j2"):
                templates.append((dirpath, file, group))
    with Progress() as bar:
        task_id = bar.add_task(
            "Apply configuration templates to devices",
            total=len(nornir.inventory.hosts) * len(templates),
        )

        def apply_templates(task: Task):
            config = ""
            for t in templates:
                if groups and not (
                    (group := t[2]) is None or group in task.host.groups
                ):
                    # Only apply templates specific to a group or templates with no group
                    bar.update(task_id, advance=1)
                    continue
                output = task.run(
                    task=template_file,
                    template=(template := t[1]),
                    path=t[0],
                    hosts=nornir.inventory.hosts,
                )
                config += output.result
                bar.console.log(f"{task.host}: {template}")
                bar.update(task_id, advance=1)
                config += "\n"
            r = task.run(
                task=napalm_configure,
                dry_run=False,
                replace=replace,
                configuration=_purge_management_config(config),
            )
            bar.console.log(
                f"{task.host}: Templates configured.{CONFIG_CHANGED if r.changed else ''}"
            )

        return nornir.run(task=apply_templates)


#########
# Tools #
#########


def configure_interfaces(nornir: nornir.core.Nornir, file: Path) -> Result:
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
            config = ""
            for interface, params in links[task.host.name].items():
                p = files(templates) / "interfaces"
                output = task.run(
                    task=template_file,
                    template="point-to-point.j2",
                    path=p,
                    interface={"name": interface, **params},
                )
                config += output.result
                bar.console.log(
                    f"{task.host}: Interface {interface} ({'IPv4' if IPV4_KEY in params else ''} {'IPv6' if IPV6_KEY in params else ''} {'ISIS' if ISIS_KEY in params else ''}): {params[DESCRIPTION_KEY]}"
                )
                bar.update(task_id, advance=1)
            r = task.run(task=napalm_configure, dry_run=False, configuration=config)
            bar.console.log(
                f"{task.host}: Interfaces configured.{CONFIG_CHANGED if r.changed else ''}"
            )

        return nornir.run(task=configure_interfaces)


def configure_peering(
    nornir: nornir.core.Nornir, group: str, neighbor_group: str
) -> Result:
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
                task=napalm_configure, dry_run=False, configuration=output.result
            )
            bar.console.log(
                f"{task.host}: Peering with {task.nornir.inventory.groups[neighbor_group].data['network_name']} configured.{CONFIG_CHANGED if r.changed else ''}"
            )
            bar.update(task_id, advance=1)

        return nornir.filter(F(groups__contains=group)).run(task=configure_peering)


CLEAN_TERMINATTR = "no daemon TerminAttr"


def onboard_cloudvision(nornir: nornir.core.Nornir) -> list[Result]:
    r = []
    with Progress() as bar:
        task_id = bar.add_task(
            "Configure TerminAttr for CloudVision onboarding",
            total=len(nornir.inventory.hosts),
        )

        def onboard_device(task: Task):
            task.run(
                task=napalm_configure, dry_run=False, configuration=CLEAN_TERMINATTR
            )
            bar.update(task_id, advance=1)

        r.append(nornir.run(task=onboard_device))
    with as_file(files(templates)) as t:
        p = t / "onboard"
        r.append(apply_templates(nornir=nornir, folder=p))
    return r


###################
# Backup to flash #
###################


DIR_FLASH_CMD = "dir flash:"
BACKUP_FILENAME = "rollback-config"


def create_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task(
            "Backup configuration to flash", total=len(nornir.inventory.hosts)
        )

        def create_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    bar.console.log(f"{task.host}: Backup already present.")
                    bar.update(task_id, advance=1)
                    return
            task.run(
                task=napalm_cli,
                commands=[f"copy running-config flash:{BACKUP_FILENAME}"],
            )
            bar.console.log(f"{task.host}: Backup created.")
            bar.update(task_id, advance=1)

        return nornir.run(task=create_backup)


def restore_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task(
            "Restore backup configuration from flash", total=len(nornir.inventory.hosts)
        )

        def restore_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    task.run(
                        task=napalm_cli,
                        commands=[f"configure replace flash:{BACKUP_FILENAME}"],
                    )
                    # Intentionally not copying running-config to startup-config here.
                    # If there is a napalm_configure following a restore, configuration will be saved.
                    # This behaviour is acceptable, user can retrieve previous configuration in startup-config
                    # in case of mis-restoring the configuration.
                    bar.console.log(f"{task.host}: Backup restored.")
                    bar.update(task_id, advance=1)
                    return
            raise Exception(f"{task.host}: Backup not found.")

        return nornir.run(task=restore_backup)


def delete_backups(nornir: nornir.core.Nornir) -> Result:
    with Progress() as bar:
        task_id = bar.add_task(
            "Delete backup on flash", total=len(nornir.inventory.hosts)
        )

        def delete_backup(task: Task):
            r = task.run(task=napalm_cli, commands=[DIR_FLASH_CMD])
            for res in r:
                if BACKUP_FILENAME in res.result[DIR_FLASH_CMD]:
                    task.run(
                        task=napalm_cli, commands=[f"delete flash:{BACKUP_FILENAME}"]
                    )
                    bar.console.log(f"{task.host}: Backup deleted.")
                    bar.update(task_id, advance=1)
                    return
            bar.console.log(f"{task.host}: Backup not found.")
            bar.update(task_id, advance=1)

        return nornir.run(task=delete_backup)


###############################
# Save and load configuration #
###############################


def save(nornir: nornir.core.Nornir, folder: Path) -> Result:
    with Progress() as bar:
        task_id = bar.add_task(
            "Save lab configuration", total=len(nornir.inventory.hosts)
        )

        def save_config(task: Task):
            task.run(task=napalm_cli, commands=["copy running-config startup-config"])
            r = task.run(task=napalm_get, getters=["config"])
            config = folder / f"{task.host}.cfg"
            folder.mkdir(parents=True, exist_ok=True)
            with open(config, "w") as file:
                file.write(r[0].result["config"]["running"])
            bar.console.log(f"{task.host}: Configuration saved to {config}")
            bar.update(task_id, advance=1)

        return nornir.run(task=save_config)


def load(nornir: nornir.core.Nornir, folder: Path) -> Result:
    with Progress() as bar:
        task_id = bar.add_task(
            "Load lab configuration", total=len(nornir.inventory.hosts)
        )

        def load_config(task: Task):
            config = folder / f"{task.host}.cfg"
            if not config.exists():
                raise Exception(
                    f"Configuration of {task.host} not found in folder {folder}"
                )
            output = task.run(
                task=template_file, template=f"{task.host}.cfg", path=folder
            )
            task.run(
                task=napalm_configure,
                dry_run=False,
                replace=False,
                configuration=_purge_management_config(output.result),
            )
            bar.console.log(f"{task.host}: Configuration loaded.")
            bar.update(task_id, advance=1)

        return nornir.run(task=load_config)
