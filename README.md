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

### How to configure the serial number and system MAC ?

cEOS does not support modifying the serial number or system MAC after the first startup. It needs to be configured before dpeloying the lab with containerlab.
Configure the [Nornir inventory](project/inventory/hosts.yaml) and run the following commands:
```
lab init-ceos
containerlab deploy
```

### How to correctly re-onboard a lab with cEOS nodes to CloudVision ?

You can destroy a lab and re-onboard it in Cloudvision but you will need to configure the same correct serial number and system MAC address for each node so CloudVision will recognize the devices as already provisioned.

To correctly re-onboard a lab previously saved to CloudVision, you need to run:
```
lab init-ceos --token cv-onboarding-token
containerlab deploy
```

> Ensure that a correct TerminAttr configuration is part of the startup config, or you can use the `lab load` command.

Then go to your CloudVision instance, `Devices -> Device Registration -> Device Onboarding -> Onboard Provisioned EOS Devices` to re-onboard the devices by provisioning the certificates.

> It is a good idea (but not mandatory) to have fixed management IP addresses defined in the `topology.clab.yml` file.

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
> Default values are defined for the `nornir.yaml` and `topology.clab.yml` files but you can specify custom file names with the `--nornir`and `--topology` options.