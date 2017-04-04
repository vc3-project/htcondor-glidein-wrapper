#!/usr/bin/env python

from __future__ import print_function
from optparse import OptionParser, OptionGroup
import urllib
import platform
import os
import errno
import sys
import logging
import tempfile
import shutil
import tarfile
import signal
import subprocess
import textwrap

__version__ = "0.9.4"

class CondorGlidein(object):
    """
    HTCondor Glidein class. 

    Default options 
    """

    def __init__(self, 
                    condor_version=None,
                    condor_urlbase=None,
                    collector=None,
                    lingertime=None,
                    loglevel=None,
                    workdir=None,
                    noclean=None,
                    exec_wrapper=None,
                    startd_cron=None
                ):
        self.condor_version = condor_version
        self.condor_urlbase = condor_urlbase
        self.collector = collector
        self.lingertime = lingertime
        self.loglevel = loglevel
        self.iwd=workdir
        self.noclean = noclean
        #if exec_wrapper is not None:
        #    self.exec_wrapper=exec_wrapper
        #if startd_cron is not None:
        #    self.startd_cron=startd_cron

        # Other items that are set later
        #self.log
        #self.condor_platform = None # condor-version-arch_distro-stripped
        #self.condor_tarball = None # the above w/ .tar.gz added
        #self.glidein_dir = None # iwd + glidein dir name
        #self.exec_wrapper = None
        #self.startd_cron = None
        

        self.setup_signaling()
        self.setup_logging(loglevel)
        self.download_tarball()
        self.setup_workdir()
        self.unpack_tarball()


        if exec_wrapper is not None:
            self.exec_wrapper = self.copy_to_exec(exec_wrapper)
        if startd_cron is not None:
            self.startd_cron = self.copy_to_exec(startd_cron)

        self.initial_config()
        if noclean is False:
            self.cleanup()

    def setup_signaling(self):
        """
        Interrupt handling to trigger the cleanup function whenever Ctrl-C
        or something like `kill` is sent to the process
        """
        signal.signal(signal.SIGINT, self.interrupt_handler)

    def setup_logging(self, loglevel):
        """
        Setup the logging handler and format
        """
        formatstr = "[%(levelname)s] %(asctime)s %(module)s.%(funcName)s(): %(message)s"
        self.log = logging.getLogger()
        hdlr = logging.StreamHandler(sys.stdout) 
        formatter = logging.Formatter(formatstr)
        hdlr.setFormatter(formatter)
        self.log.addHandler(hdlr)
        self.log.setLevel(loglevel)
        
    def setup_workdir(self):
        """ 
        Setup the working directory for the HTCondor binaries, configs, etc. 
        
        If no argument is passed, then generate a random one in the current
        working directory. Otherwise use the path specified
        """
        if self.iwd is None:
            self.iwd = os.getcwd()

        try:
            self.glidein_dir = tempfile.mkdtemp(prefix="%s/condor-glidein." % self.iwd)
            self.log.info("Glidein working directory is %s" % self.glidein_dir)
            # Create the "local" directory for anything non-vanilla
            self.glidein_local_dir = self.glidein_dir + "/local"
            os.mkdir(self.glidein_local_dir)
            self.log.debug("Glidein local directory is %s" % self.glidein_local_dir)
        except Exception as e:
            self.log.debug(e)
            self.log.error("Failed to create working directory")
            self.cleanup()

    def download_tarball(self):
        """
        Determine the worker's architecture and distribution, download the 
        appropriate release of HTCondor. 
        """
    
        if platform.machine() == 'x86_64':
            arch = platform.machine()
        else:
            self.log.error("Only x86_64 architecture is supported")
            raise Exception

        condor_version = self.condor_version

        distro_name = platform.linux_distribution()[0]
        distro_major = platform.linux_distribution()[1].split(".",1)[0]
         
        if platform.system() == 'Linux':
            if "Scientific" or "CentOS" or "Red Hat" in distro_name:
                distro = "RedHat" + distro_major
            elif "Debian" in distro_name:
                distro = "Debian" + distro_major
            elif "Ubuntu" in distro_name:
                distro = "Ubuntu" + distro_major
            else:
                raise Exception("Unable to determine distro")
        elif platform.system() == 'Darwin':
                distro = 'MacOSX' # why not?

        self.condor_platform = "condor-%s-%s_%s-stripped" % (condor_version,
                                                        arch, distro)

        tarball_name = self.condor_platform + ".tar.gz"

        src = self.condor_urlbase + "/" + tarball_name

        self.condor_tarball = os.getcwd() + "/" + tarball_name

        self.log.info("Downloading HTCondor tarball")
        self.log.debug("%s > %s", src, self.condor_tarball)

        try:
            urllib.urlretrieve(src, self.condor_tarball) 
        except Exception as e:
            self.log.debug(e)
            self.log.error("Failed to retrieve the tarball")
            self.cleanup()

        cmd = "file %s" % self.condor_tarball
        out = self.runcommand(cmd)
        if "gzip compressed data" in out:
            self.log.debug("Filetype is gzip")
        else:
            self.log.error("File type is incorrect. Aborting.")
            self.cleanup()

    def unpack_tarball(self):
        """
        Unpack the HTCondor tarball to glidein_dir and cleanup the tar file

        """
        #condor_dir SHOULD be the same as self.glidein_dir/self.condor_platform
        try:
            tar = tarfile.open(self.condor_tarball)
            tar.extractall(path=self.glidein_dir + '/')
            condor_dir = self.glidein_dir + '/' + tar.getnames()[0]
            self.log.debug("Unpacked tarball to %s", condor_dir)
            tar.close()

            os.remove(self.condor_tarball)
        except Exception as e:
            self.log.debug(e)
            self.log.error("Failed to unpack the tarball")
            self.cleanup()

    def copy_to_exec(self, path):
        """
        If we need to add some extra scripts such as periodic crons or exec 
        wrappers, we move them to the HTCondor libexec dir and make sure they
        are executable
        """
        # Make the VC3 libexec dir if its not available already
        try: 
            local_libexec = self.glidein_local_dir + "/libexec"
            os.mkdir(local_libexec)
        except OSError as e:
            if e.errno == errno.EEXIST:
                self.log.debug("Local libexec dir already exists")
                pass
            else:
                self.log.error("Couldn't create local libexec: %s", e)
                self.cleanup()
        self.log.debug("Created or found local libexec path: %s", local_libexec)
        
        try:
            f = self.realize_file(path, local_libexec) # copy file from http or 
                                                     # unix to local_libexec/
            self.log.debug("Copied %s to %s: ", path, f)
        except Exception as e:
            self.log.error("Couldn't copy to libexec: %s", e)
            self.cleanup()
    
        try:
            os.chmod(f, 0755)
            self.log.debug("Set %s as executable", f)
        except Exception as e:
            self.log.error("Couldn't set execute bits on %s: %s", f, e)

        return f

        
    def cleanup(self):
        """
        Remove any files that may have been created at glidein start time

        Some operations are not atomic, e.g., deleting the tarball after
        extracting it. Make sure we clean this up!
        """ 
        if self.noclean is True:
            self.log.info("'No Clean' is true -- exiting without cleaning up!")
            sys.exit(1)

        self.log.info("Removing working directory and leftover files")

        try:
            os.remove(self.condor_tarball)
        except OSError as e:
            if e.errno == errno.ENOENT:
                self.log.debug("Tarball already cleaned up.")
            else:
                self.log.warn("Tarball exists but can't be removed for some reason")
            pass

        try:
            shutil.rmtree(self.glidein_dir)
        except AttributeError:
            self.log.debug("Working directory is not yet defined -- ignoring")
            pass
        except:
            self.log.warn("Failed to remove %s !" % self.glidein_dir)
            pass
        sys.exit(1)

    def initial_config(self):
        """
        Write out a basic HTCondor config to 
            <glidein_dir>/<local.hostname>/etc/condor/glidein.conf

        This configuration can later be overwritten by a startd cron that
        checks for additional config.
        """
        config_bits = []

        dynamic_config = """ 
            COLLECTOR_HOST = %s
            STARTD_NOCLAIM_SHUTDOWN = %s
            START = %s
            GLIDEIN_LOCAL_DIR = %s 
        """ % (self.collector, self.lingertime, "TRUE", self.glidein_local_dir)

        config_bits.append(textwrap.dedent(dynamic_config))

        static_config = """
            SUSPEND                     = FALSE
            PREEMPT                     = FALSE
            KILL                        = FALSE
            RANK                        = 0
            CLAIM_WORKLIFE              = 3600
            JOB_RENICE_INCREMENT        = 0
            HIGHPORT                    = 30000
            LOWPORT                     = 20000
            DAEMON_LIST                 = MASTER, STARTD 
            ALLOW_WRITE                 = condor_pool@*, submit-side@matchsession
            SEC_DEFAULT_AUTHENTICATION  = REQUIRED
            SEC_DEFAULT_ENCRYPTION      = REQUIRED
            SEC_DEFAULT_INTEGRITY       = REQUIRED
            ALLOW_ADMINISTRATOR         = condor_pool@*/*
        """

        config_bits.append(textwrap.dedent(static_config))

        if hasattr(self, 'exec_wrapper'):
            wrapper = "USER_JOB_WRAPPER = $(GLIDEIN_LOCAL_DIR)/libexec/%s" % (os.path.basename(self.exec_wrapper))
            config_bits.append(wrapper)
        if hasattr(self, 'startd_cron'):
            cron = """
                STARTD_CRON_JOBLIST          = $(STARTD_CRON_JOBLIST) generic
                STARTD_CRON_generic_EXECUTABLE = $(GLIDEIN_LOCAL_DIR)/libexec/%s
                STARTD_CRON_generic_PERIOD   = 5m
                STARTD_CRON_generic_MODE     = PERIODIC
                STARTD_CRON_generic_RECONFIG = TRUE
                STARTD_CRON_generic_KILL     = TRUE
                STARTD_CRON_generic_ARGS     = NONE 
            """ % ( os.path.basename(self.startd_cron) )
            config_bits.append(textwrap.dedent(cron))

        config = "".join(config_bits)
        config_dir = self.glidein_local_dir + "/etc/condor"
        config_path = config_dir + "/glidein.conf"

        self.log.debug("Configuration built: %s " % config)

        try:
            self.log.debug("config_dir is: %s" % config_dir)            
            os.makedirs(config_dir)
        except Exception as e:
            self.log.error("Unable to create configuration dir: %s" % config_dir)
            self.log.debug(e)
            self.cleanup()

        try:
            target = open(config_path, 'w')
            target.write(config)
            target.close()
            self.log.debug("Wrote %s" % config_path)
        except Exception as e:
            self.log.error("Unable to write config %s" % config_path)
            self.log.debug(e)
            self.cleanup()

    #
    # Utilities
    #

    def interrupt_handler(self, signal, frame):
        """
        Simply catches signals and runs the cleanup script
        """
        self.log.info("Caught signal, running cleanup")
        self.cleanup()
        sys.exit(1)

    def runcommand(self, cmd):
        """
        Helpful little function to run external *nix commands
        """
        self.log.debug("cmd = %s" % cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = p.communicate()
        out = out.rstrip()
        if p.returncode == 0:
            self.log.debug("External command output: %s" % out)
        else:
            self.log.error("External command failed: %s" % err)
            self.cleanup()
        return out

    def realize_file(self, src_file, dest_dir):
        """
        This function takes a UNIX path or HTTP path and returns a real file
        path.

        If the file is an HTTP file, then it downloads it to the cwd and 
        returns that path
        """
        
        d = dest_dir + "/" + os.path.basename(src_file)

        if src_file.startswith('http'):
            try:
                # This is a bit tricky, but we exploit the fact that basename()
                # is simply a string splitter. Could be fixed up to be nicer
                urllib.urlretrieve(src_file, d)
                return d
            except:
                self.log.error("Cannot retrieve file %s", src_file)
        else:
            shutil.copyfile(os.path.realpath(src_file), d)
            return d
             

if __name__ == '__main__':

    usage = "python glidein2.py"
    parser = OptionParser(usage, version="%prog " + __version__ )
    
    parser.set_defaults(
            workdir=None,
            condor_version="8.6.0",
            condor_urlbase="http://download.virtualclusters.org/repository",
            collector="condor.grid.uchicago.edu:9618",
            linger=600,
            auth="password",
            password_file=None,
            noclean=False,
            exec_wrapper=None,
            loglevel=20)
             
    
    ggroup = OptionGroup(parser, "Glidein options",
        "Control the HTCondor source and configuration")

    ggroup.add_option("-w", "--workdir", action="store", type="string",
         dest="workdir", help="Path to the working directory for the glidein")

    ggroup.add_option("-V", "--condor-version", action="store", type="string",
         dest="condor_version", help="HTCondor version")

    ggroup.add_option("-r", "--repo", action="store", type="string",
         dest="condor_urlbase", help="URL containing the HTCondor tarball")

    ggroup.add_option("-c", "--collector", action="store", type="string",
         dest="collector", 
         help="collector string e.g., condor.grid.uchicago.edu:9618")

    ggroup.add_option("-x", "--lingertime", action="store", type="int",
         dest="linger", help="idletime in seconds before self-shutdown")

    ggroup.add_option("-a", "--auth", action="store", type="string",
         dest="auth", help="Authentication type (e.g., password, GSI)")

    ggroup.add_option("-p", "--passwordfile", action="store", type="string",
         dest="password_file", help="Path to the HTCondor pool password file")

    ggroup.add_option("-W", "--wrapper", action="store", type="string",
         dest="wrapper", help="Path to user job wrapper file")

    ggroup.add_option("-P", "--periodic", action="store", type="string",
         dest="periodic", help="Path to user periodic classad hook script")


    parser.add_option_group(ggroup)

    # Since we're using constants anyway, just use the logging levels numeric
    # values as provided by logger
    # 
    # DEBUG=10
    # INFO=20
    # NOTSET=0

    vgroup = OptionGroup(parser,"Logging options", 
        "Control the verbosity of the glidein")

    vgroup.add_option("-v", "--verbose", action="store_const", const=20, dest="loglevel",
        help="Sets logger to INFO level (default)")
    vgroup.add_option("-d", "--debug", action="store_const", const=10, dest="loglevel",
        help="Sets logger to DEBUG level")

    parser.add_option_group(vgroup)

    mgroup = OptionGroup(parser, "Misc options",
        "Debugging and other options")
    
    mgroup.add_option("-n", "--no-cleanup", action="store_true", 
        dest="noclean", help="Do not clean up glidein files after exit")
    

    parser.add_option_group(mgroup)

    (options, args) = parser.parse_args()

    gi = CondorGlidein(
        condor_version=options.condor_version,
        condor_urlbase=options.condor_urlbase,
        collector=options.collector,
        lingertime=options.linger,
        noclean=options.noclean,
        workdir=options.workdir,
        loglevel=options.loglevel,
        exec_wrapper=options.wrapper,
        startd_cron=options.periodic
    )
    
