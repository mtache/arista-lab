# Containerlab tooling

Simple Python script for managing EOS configuration of containerlab topologies.

```
Usage: lab [OPTIONS] COMMAND [ARGS]...

Options:
  -n, --nornir PATH        Nornir configuration in YAML format.
  -t, --topology FILENAME  Containerlab topology file.
  --help                   Show this message and exit.

Commands:
  backup   Create or delete device configuration backups to flash
  load     Load lab configuration from a folder
  onboard  Onboard lab to CloudVision
  restore  Restore configuration backups from flash
  save     Save lab configuration to a folder
```

## Installation and usage

Requires poetry to build the wheel.
You can use poetry to build the package with `poetry build` and install the package with `pip` or use the command `make all`.

## Project folder

This repo provides a project example skeleton to use with this tool:
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
The default value in the lab tool are defined for the `nornir.yaml` and `topology.yaml` file. So the command `lab backup` will backup all device running-configuration to flash. The command `lab load --folder configs/lsl3-fabric` will load a L3LS fabric configuration initially generated with CloudVision Studios.