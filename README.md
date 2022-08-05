# Containerlab tooling

Simple Python script for managing cEOS configuration of containerlab topologies.

```
Usage: lab [OPTIONS] COMMAND [ARGS]...

Options:
  -n, --nornir PATH        Nornir configuration in YAML format.
  -t, --topology FILENAME  Containerlab topology file.
  --help                   Show this message and exit.

Commands:
  backup   Create or delete device configuration backups to flash
  init     Configure cEOS Serial Number and System MAC address from...
  load     Load lab configuration from a folder
  onboard  Onboard lab to CloudVision
  restore  Restore configuration backups from flash
  save     Save lab configuration to a folder
```

## Installation and usage

Requires poetry to build the wheel.
You can use poetry to build the package with `poetry build` and install the package with `pip` or use the command `make all`.

## Project folder

This repo provides a [project example skeleton](project) to use with this tool:
```
├── clab-ceos-fabric (Containerlab topology directory - contains binds to device flash)
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
├── configs (arbitraty folder used to store configurations)
│   └── l3ls-fabric
│       ├── leaf1.cfg
│       ├── leaf2.cfg
│       ├── leaf3.cfg
│       ├── leaf4.cfg
│       ├── spine1.cfg
│       └── spine2.cfg
├── cv-onboarding-token (optional CVaaS token to onboard the devices)
├── inventory (contains Nornir inventory data)
│   ├── defaults.yaml
│   ├── groups.yaml
│   └── hosts.yaml
├── nornir.yaml (default Nornir configuration)
└── topology.yaml (Containerlab topology file)
```
The default value in the lab tool are defined for the `nornir.yaml` and `topology.yaml` files but you can specify custom files with the `--nornir`and `--topology` options.

## How to manage lab configuration ?

The command `lab backup` will backup all device running-configuration to flash. You can restore it anytime with `lab restore`.
The command `lab load --folder configs/lsl3-fabric` will load a L3LS fabric configuration initially generated with CloudVision Studios.
Some commands like `lab load` or `lab onboard` will automatically save configuration to flash, respectively before and after running the command.

> Once the backup configuration is present in flash, it won't be overriden unless you run `lab backup --delete`

## How to configure the serial number and system MAC ?

cEOS does not support modifying the serial number or system MAC after the first startup. It needs to be configured before dpeloying the lab with containerlab.
Configure the [Nornir inventory](project/inventory/hosts.yaml) and run the following commands:
```
lab init
containerlab deploy -t topology.yaml
```

## How to onboard the lab to CloudVision-as-a-service ?

Create a file with a generated secure token. Use the command `lab onboard --token cv-onboarding-token` to configure the lab and start to stream to CloudVision.
You can destroy a lab and re-onboard it after but you will need to configure the serial number for each node so CloudVision will recognize the devices as previously onboarded.

To correctly re-onboard a lab previously saved to CloudVision, you need to run:
```
lab init
containerlab deploy -t topology.yaml
lab onboard --token cv-omnboarding-token
lab load --folder configs/my-lab
```