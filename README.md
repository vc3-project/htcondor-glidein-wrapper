# vc3-glidein

[![Codacy Badge](https://api.codacy.com/project/badge/Grade/69cfa4b889b242df977fbce919312fa5)](https://www.codacy.com/app/LincolnBryant/vc3-glidein?utm_source=github.com&utm_medium=referral&utm_content=vc3-project/vc3-glidein&utm_campaign=badger)

Current version: v1.5.2

```
Usage: ./vc3-glidein

Options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit

  Glidein options:
    Control the HTCondor source and configuration

    -w WORKDIR, --workdir=WORKDIR
                        Path to the working directory for the glidein
    -V CONDOR_VERSION, --condor-version=CONDOR_VERSION
                        HTCondor version
    -r CONDOR_URLBASE, --repo=CONDOR_URLBASE
                        URL containing the HTCondor tarball
    -c COLLECTOR, --collector=COLLECTOR
                        collector string e.g., condor.virtualclusters.org:9618
    -C CCB, --ccb=CCB   ccb string e.g., condor.virtualclusters.org:9618
    -x LINGER, --lingertime=LINGER
                        idletime in seconds before self-shutdown
    -a AUTH, --auth=AUTH
                        Authentication type (e.g., password, GSI)
    -p PASSWORDFILE, --password=PASSWORDFILE
                        HTCondor pool password file
    -e EXTRA_CONFIG, --extra-config=EXTRA_CONFIG
                        Additional configuration
    -W WRAPPER, --wrapper=WRAPPER
                        Path to user job wrapper file
    -E VC3_ENV, --vc3-env=VC3_ENV
                        Name of environment varible that points to a file with
                        the VC3 environment
    -P PERIODIC, --periodic=PERIODIC
                        Path to user periodic classad hook script
    -t, --partitionable
                        Enables partitionable slots
    -s SLOTS, --slots=SLOTS
                        Enable fixed number of slots
    -D CORES, --cores=CORES
                        Total number of cores to be used by the glidein.
    -m MEMORY, --memory=MEMORY
                        Total memory (MiB) in glidein.
    -F DISK, --disk=DISK
                        Total disk (KiB) in glidein.
    -i GLIDEIN_ID, --id=GLIDEIN_ID
                        Unique Glidein ID
    -T TOKENFILE, --token=TOKENFILE
                        HTCondor pool token file


  Logging options:
    Control the verbosity of the glidein

    -v, --verbose       Sets logger to INFO level (default)
    -d, --debug         Sets logger to DEBUG level

  Misc options:
    Debugging and other options

    -n, --no-cleanup    Do not clean up glidein files after exit
```
