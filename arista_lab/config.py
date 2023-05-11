from pathlib import Path
import re
from os import walk
from openpyxl import load_workbook
from importlib.resources import files
from arista_lab import templates
from datetime import datetime, timedelta

import requests
import ipaddress
import nornir
from nornir.core.task import Task, Result
from nornir.core.filter import F
from rich.progress import Progress

from nornir_napalm.plugins.tasks import napalm_cli, napalm_configure, napalm_get
from nornir_jinja2.plugins.tasks import template_file

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
                r = task.run(
                    task=napalm_configure,
                    dry_run=False,
                    replace=replace,
                    configuration=_purge_management_config(output.result),
                )
                bar.console.log(
                    f"{task.host}: {template} template configured.{CONFIG_CHANGED if r.changed else ''}"
                )
                bar.update(task_id, advance=1)

        return nornir.run(task=apply_templates)

#########
# Tools #
#########


def configure_interfaces(nornir: nornir.core.Nornir, file: Path) -> Result:
    LINK_PARAM = ["ISIS Instance", "ISIS Metric"]
    INTERFACE_PARAM = ["Device", "Interface", "IPv4 Address", "IPv6 Address"]
    DESCRIPTION = "description"

    def _parse_ip_plan(file: Path):
        interfaces = {}
        workbook = load_workbook(filename=file, read_only=True)
        sheet = workbook.active

        def links(sheet):
            rows = sheet.rows
            columns = [c.value for c in next(rows)]
            for row in rows:
                values = [c.value for c in row]
                yield dict(zip(columns, values))

        # Create a dictionnary to configure interfaces on a given device
        for link in links(sheet):
            for device_id, neighbor_id in (range(1, 3), range(2, 0, -1)):
                device = link[f"{INTERFACE_PARAM[0]} {device_id}"]
                interface = link[f"{INTERFACE_PARAM[1]} {device_id}"]
                neighbor = link[f"{INTERFACE_PARAM[0]} {neighbor_id}"]
                neighbor_interface = link[f"{INTERFACE_PARAM[1]} {neighbor_id}"]
                if device not in interfaces:
                    interfaces[device] = {}
                interfaces[device][interface] = {
                    DESCRIPTION: f"to {neighbor} {neighbor_interface}",
                    INTERFACE_PARAM[2]: link[f"{INTERFACE_PARAM[2]} {device_id}"],
                    INTERFACE_PARAM[3]: link[f"{INTERFACE_PARAM[3]} {device_id}"],
                    LINK_PARAM[0]: link[f"{LINK_PARAM[0]}"],
                    LINK_PARAM[1]: link[f"{LINK_PARAM[1]}"],
                }
        workbook.close()
        return interfaces

    ip_plan = _parse_ip_plan(file)
    with Progress() as bar:
        task_id = bar.add_task(
            "Configure point-to-point interfaces", total=len(nornir.inventory.hosts)
        )

        def configure_interfaces(task: Task):
            config = ""
            for interface, params in ip_plan[task.host.name].items():
                config += (
                    f"interface {interface}\n"
                    + "no switchport\n"
                    + f"description {params[DESCRIPTION]}\n"
                )
                if params[INTERFACE_PARAM[2]]:
                    config += f"ip address {params[INTERFACE_PARAM[2]]}\n"
                if params[INTERFACE_PARAM[3]]:
                    config += f"ipv6 address {params[INTERFACE_PARAM[3]]}\n"
                if params[LINK_PARAM[0]]:
                    config += (
                        f"isis enable {params[LINK_PARAM[0]]}\n"
                        + "isis network point-to-point\n"
                    )
                    if params[LINK_PARAM[1]]:
                        config += f"isis metric {params[LINK_PARAM[1]]}\n"
                r = task.run(
                    task=napalm_configure,
                    dry_run=False,
                    replace=False,
                    configuration=config,
                )
                bar.console.log(
                    f"{task.host}: Point-to-point interfaces configured.{CONFIG_CHANGED if r.changed else ''}"
                )
                bar.update(task_id, advance=1)

        return nornir.run(task=configure_interfaces)


def configure_peering(nornir: nornir.core.Nornir, group: str, neighbor_group: str) -> Result:

    def _get_announced_prefixes(asn: int):
        start_time = datetime.now() - timedelta(days = 10)
        url = f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}&starttime={start_time.strftime('%Y-%m-%dT%H:%M')}"
        r = requests.get(url)
        if r.ok:
            prefixes = []
            for prefix in r.json()["data"]["prefixes"]:
                prefixes.append(prefix["prefix"])
            return prefixes
        else:
            raise Exception(f'Could not get announced prefixes for AS{asn}')

    def _build_networks_vars(networks):
        networks = [ipaddress.ip_network(p) for p in networks]
        for network in networks:
            if any(network != n and network.overlaps(n) for n in networks):
                networks.remove(network)

        hosts = []
        hosts_ipv6 = []
        prefixes = []
        prefixes_ipv6 = []
        for network in networks:
            if network.version == 4:
                hosts.append(f'{next(network.hosts())}/{network.prefixlen}')
                prefixes.append(str(network))
            elif network.version == 6:
                hosts_ipv6.append(f'{next(network.hosts())}/{network.prefixlen}')
                prefixes_ipv6.append(str(network))

        return {'hosts': hosts,
                'hosts_ipv6': hosts_ipv6,
                'prefixes': hosts,
                'prefixes_ipv6': hosts_ipv6}

    with Progress() as bar:
        task_id = bar.add_task(
            "Configure peering devices", total=len(nornir.inventory.children_of_group(group))
        )

        def configure_peering(task: Task):
            MAX_LOOPBACKS = 2100
            vars = _build_networks_vars(_get_announced_prefixes(task.host.data['asn']))
            vars.update({'name': task.host.data['isp'],
                         'asn': task.host.data['asn'],
                         'description': task.host.data['description'],
                         'as_path_length': task.host.data['as_path_length'],
                         'max_loopback': MAX_LOOPBACKS,
                         'neighbor_name': task.nornir.inventory.groups[neighbor_group].data['network_name'],
                         'neighbor_ipv4': task.host.data['neighbor_ipv4'],
                         'neighbor_ipv6': task.host.data['neighbor_ipv6'],
                         'neighbor_as': task.nornir.inventory.groups[neighbor_group].data['asn']
                         })
            p = files(templates) / 'peering'
            output = task.run(task=template_file, template='isp.j2', path=p, vars=vars)
            r = task.run(task=napalm_configure, dry_run=False, configuration=output.result)
            bar.console.log(f"{task.host}: Peering with {task.nornir.inventory.groups[neighbor_group].data['network_name']} configured.{CONFIG_CHANGED if r.changed else ''}")
            bar.update(task_id, advance=1)

        return nornir.filter(F(groups__contains=group)).run(task=configure_peering)


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
