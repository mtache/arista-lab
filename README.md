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