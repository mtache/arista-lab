# Arista Lab Tools

Python scripts to manage/generate EOS configuration for labs.
Based on [Nornir](https://nornir.tech/) and [NAPALM](https://napalm.readthedocs.io/), integrates well with [containerlab](https://containerlab.srlinux.dev/) for cEOS labs but can also be used for vEOS or physical labs.

```
Usage: lab [OPTIONS] COMMAND [ARGS]...

Options:
  -n, --nornir PATH        Nornir configuration in YAML format.
  -t, --topology FILENAME  Containerlab topology file.
  --help                   Show this message and exit.

Commands:
  apply       Apply configuration templates
  backup      Create or delete device configuration backups to flash
  init-ceos   Configure cEOS serial number, system MAC address and copy CloudVision token to flash
  interfaces  Configure point-to-point interfaces
  load        Load configuration from a folder
  peering     Configure peering devices
  restore     Restore configuration backups from flash
  save        Save configuration to a folder
  start       Start containers
  stop        Stop containers
```

## Installation

```
pip install arista-lab
```

## Usage

### How to backup lab configuration ?

The command `lab backup` will backup all device running-configuration to flash. You can restore it anytime with `lab restore`.
Some commands like `lab load` or `lab apply` will automatically save configuration to flash before running the command.

> Once the backup configuration is present in flash, it won't be overriden unless you run `lab backup --delete`

### How to save lab configuration to a local folder ?

The command `lab loads --folder configs` will save the configuration of all lab devices to the `configs` folder.
The command `lab load --folder configs` will **merge** the device configurations in the folder with the running configurations.

> The `Management` interface configuration is always removed from the configuration files being loaded.

### How to configure point-to-point links ?

Use the `lab interfaces` command. The command takes a YAML file as input that defines the point-to-point IP subnet and eventually the IGP metrics and instance name.
Below is the YAML file structure. Refer to project example below for more details.

``` yaml
links:
  - endpoints: ["bas:et1", "ban:et1"]
    ipv4_subnet: 10.186.59.0/31
    ipv6_subnet: fc00:10:186:59::/127
    isis:
      instance: ISIS
      metric: 1
```

## Project skeleton

The structure below provides an example on how to structure a lab project:
```
.
├── clab-evpn-vxlan-fabric (containerlab topology directory - contains binds to device flash)
│   ├── ansible-inventory.yml
│   ├── leaf1
│   │   └── flash
│   ├── leaf2
│   │   └── flash
│   ├── leaf3
│   │   └── flash
│   ├── leaf4
│   │   └── flash
│   ├── spine1
│   │   └── flash
│   └── spine2
│       └── flash
├── Makefile (contains useful targets)
├── configs (arbitrary folder used to store configurations)
│   └── evpn-vxlan-fabric
│       ├── leaf1.cfg
│       ├── leaf2.cfg
│       ├── leaf3.cfg
│       ├── leaf4.cfg
│       ├── spine1.cfg
│       └── spine2.cfg
├── cv-onboarding-token (optional CloudVision token to onboard the devices)
├── inventory (contains Nornir inventory data)
│   ├── defaults.yaml
│   ├── groups.yaml
│   └── hosts.yaml
├── nornir.yaml (default Nornir configuration)
├── links.yaml (point-to-point links definition for the 'lab interfaces' command)
├── startup (arbitrary folder used to store startup configurations)
│   ├── leaf1.cfg
│   ├── leaf2.cfg
│   ├── leaf3.cfg
│   ├── leaf4.cfg
│   ├── spine1.cfg
│   └── spine2.cfg
└── topology.clab.yml (containerlab topology file)
```