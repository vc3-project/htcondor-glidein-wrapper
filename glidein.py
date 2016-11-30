#!/bin/env python
#
# General-purpose Condor glidein job wrapper, configurable by command line
#  arguments. Supports password and GSI auth. 
#
__author__ = "John Hover, Jose Caballero"
__copyright__ = "2014 John Hover, Jose Caballero"
__credits__ = []
__license__ = "GPL"
__version__ = "0.9.3"
__maintainer__ = "John Hover, Jose Caballero"
__email__ = "jhover@bnl.gov, jcaballero@bnl.gov"
__status__ = "Development"


import getopt
import logging
import os
import shutil
import signal
import socket
import string
import subprocess 
import sys
import tempfile
import time
import urllib

class CondorGlidein(object):
    
    def __init__(self, condor_version="8.0.6",
                       condor_urlbase="http://dev.racf.bnl.gov/dist/condor",
                       collector="gridtest05.racf.bnl.gov",
                       port="29618",

                       auth=["fs"], 
                       #token="changeme", 
                       gsitoken=None, 
                       passwdtoken="changeme", 

                       linger="300", 
                       startexpression="TRUE",

                       loglevel=logging.DEBUG,
                       noclean=False ):
        
        self.condor_version = condor_version
        self.condor_urlbase = condor_urlbase
        self.collector = collector
        self.collector_port = port
        self.linger = linger
        self.startexpression = startexpression

        self.auth = auth
        self.gsitoken=gsitoken
        self.authlist = None
        if self.gsitoken:
            self.authlist = self.gsitoken.split(',')
        self.passwdtoken=passwdtoken

        self.noclean = noclean

        #if self.auth.lower() == 'password':
        #    self.password = token
        #elif self.auth.lower() == 'gsi':
        #    self.authtok = token
        #    self.authlist = self.authtok.split(',')
        #else:
        #    raise Exception("Invalid auth type: % self.auth")

        
        try:        
            self.setup_logging(loglevel)
            self.report_args()
            self.report_info()
            self.setup_dir()
            self.set_short_hostname()
            self.handle_tarball()
            self.install_condor()
            self.configure_condor()
        except Exception, ex:
            self.log.error("Exception caught during initialization.")
            raise ex           

    def setup_logging(self, loglevel):
        major, minor, release, st, num = sys.version_info
        FORMAT23="[ %(levelname)s ] %(asctime)s %(filename)s (Line %(lineno)d): %(message)s"
        FORMAT24=FORMAT23
        FORMAT25="[%(levelname)s] %(asctime)s %(module)s.%(funcName)s(): %(message)s"
        FORMAT26=FORMAT25
        
        if major == 2:
            if minor ==3:
                formatstr = FORMAT23
            elif minor == 4:
                formatstr = FORMAT24
            elif minor == 5:
                formatstr = FORMAT25
            elif minor == 6:
                formatstr = FORMAT26
            else:
                formatstr = FORMAT26
        self.log = logging.getLogger()
        hdlr = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(formatstr)
        hdlr.setFormatter(formatter)
        self.log.addHandler(hdlr)
        self.log.setLevel(loglevel)


    def report_info(self):
        self.log.info("Hostname: %s" % socket.gethostname())
        keys = os.environ.keys()
        keys.sort()
        envstr = ""
        for i in keys:
            envstr += " %s=%s\n" % (i,os.environ[i])
        self.log.debug("Environment:\n %s" % envstr)

    def report_args(self):
        self.log.debug("condor_version: %s" % self.condor_version)
        self.log.debug("collector: %s" % self.collector)
        self.log.debug("collector_port: %s" % self.collector_port)
        self.log.debug("auth: %s" % self.auth)
        # FIXME 
        #if self.auth == "gsi":
        #    self.log.debug("authtok: %s" % self.authtok)
        #self.log.debug("linger: %s" % self.linger)

    
    def setup_dir(self):
        self.iwd = os.getcwd()
        self.log.info("Working directory is %s" % self.iwd )
        self.condor_dir = tempfile.mkdtemp(prefix="%s/condor-glidein." % self.iwd)
        self.log.info("Condor directory is %s" % self.condor_dir )


    # --------------------------------------------------------------
    #       Get tarball 
    # --------------------------------------------------------------

    def handle_tarball(self):
        platform="RedHat6"
        arch="x86_64" 
        os.chdir(self.condor_dir)
        tarball_name = "condor-%s-%s_%s-stripped.tar.gz" % (condor_version, 
                                                            arch, 
                                                            platform)
        self.log.debug("tarball file is %s" % tarball_name)
        tarball_url = "%s/%s" % (self.condor_urlbase, 
                                          tarball_name)
        self.log.info("Retrieving Condor from %s" % tarball_url)

        try:
            self._get_tarball(tarball_url, tarball_name)
        except:
            raise Exception("Tarball cannot be retrieved. Aborting.")

        
        cmd = "file %s" % tarball_name
        out = self.runcommand(cmd)
        if "gzip compressed data" in out:
            self.log.debug("Filetype contains gzip.")
        else:
            raise Exception("File type incorrect. Failed. ")
        
        self.log.info("Download complete. File OK.")
        self.log.info("Untarring Condor...")
        cmd = "tar --verbose --extract --gzip --strip-components=1  --file=%s " % tarball_name
        self.runcommand(cmd)
        self.log.info("Untarring successful.")


    def _get_tarball(self, src, dest):

        for path in src.split(','):

            if path.startswith('http'):
                try:
                    self._get_uri_tarball(path, dest)
                    return
                except:
                    self.log.error('Unable to get tarball from %s' %path)

            if path.startswith('file'):
                try:
                    # path is file:///....
                    _path = path[7:]
                    self._get_fs_tarball(_path, dest)
                    return
                except:
                    self.log.error('Unable to get tarball from %s' %path)

        # if loop exahusted and we did not return, something failed...
        self.log.critical('Unable to get the tarball')
        raise Exception('Unable to get the tarball')


    def _get_uri_tarball(self, src, dest):
        try:
            urllib.urlretrieve(src, dest)
        except Exception, ex:
            self.log.error("Exception trying to get tarball from src %s: %s" % (src, ex))
            raise ex

    def _get_fs_tarball(self, src, dest):
        try:
            shutil.copyfile(src, dest)
        except Exception, ex:
            self.log.error("Exception trying to get tarball from src %s: %s" % (src, ex))
            raise ex

    # --------------------------------------------------------------




    def set_short_hostname(self):
        self.log.debug("Determining short hostname...")
        shn=""
        hn = socket.gethostname()
        dotidx = hn.find('.')
        if dotidx > 0:
            shn = hn[:dotidx]
        elif dotidx < 0:
            shn = hn
        else:
            raise Exception("Problem with hostname dot location.")
        self.short_hostname = shn
        self.log.debug("Short hostname is %s" % self.short_hostname)

    def populate_gridmap(self):
        gmfpath = "%s/grid-mapfile" % self.condor_dir 
        self.log.info("Creating grid-mapfile: %s" % gmfpath)
        gms = ""
        for n in self.authlist:
            n = n.strip()
            gms += '"%s" condor_pool\n' % n
        gmf = open(gmfpath, 'w')
        gmf.write(gms)
        gmf.close()
        self.log.debug("Created grid-mapfile: %s\n%s\n" % (gmfpath, gms))

    def install_condor(self): 
        cmd = "./condor_install --type=execute"
        self.log.info("Running condor_install: '%s'" % cmd)
        os.chdir(self.condor_dir)
        self.runcommand(cmd)
        os.environ["CONDOR_CONFIG"] = "%s/etc/condor_config" % self.condor_dir
        
        self.log.info("Making config dir: %s/local.%s/config" % (self.condor_dir, 
                                                                 self.short_hostname))
        try:
            os.makedirs( "%s/local.%s/config" % (self.condor_dir, self.short_hostname))
        except OSError, oe:
            self.log.debug("Caught OS error creating local config dir. Already exists.")
        
        self.log.info("Condor installed.")    

    def configure_condor(self):
        lconfig = "%s/local.%s/condor_config.local" % (self.condor_dir, 
                                                       self.short_hostname)
        self.log.info("Local config file will be %s" % lconfig)

        cfs = ""
        cfs += "COLLECTOR_HOST=%s:%s\n" % (self.collector, self.collector_port)
        cfs += "STARTD_NOCLAIM_SHUTDOWN = %s\n" % self.linger
        cfs += "START = %s\n" %self.startexpression
        cfs += "SUSPEND = FALSE\n"
        cfs += "PREEMPT = FALSE\n"
        cfs += "KILL = FALSE\n"
        cfs += "RANK = 0\n"
        cfs += "CLAIM_WORKLIFE = 3600\n"        
        cfs += "JOB_RENICE_INCREMENT=0\n"     
        cfs += "GSI_DELEGATION_KEYBITS = 1024\n"         
        cfs += "CCB_ADDRESS = $(COLLECTOR_HOST)\n" 
        cfs += "HIGHPORT = 30000\n" 
        cfs += "LOWPORT = 20000\n"         
        cfs += "DAEMON_LIST =  MASTER STARTD\n" 
        cfs += "ALLOW_WRITE = condor_pool@*\n" 
        cfs += "SEC_DEFAULT_AUTHENTICATION = OPTIONAL\n" 
        cfs += "SEC_DEFAULT_AUTHENTICATION_METHODS = CLAIMTOBE\n" 
        cfs += "SEC_ENABLE_MATCH_PASSWORD_AUTHENTICATION  = True\n" 
        cfs += "SEC_DEFAULT_ENCRYPTION = REQUIRED\n" 
        cfs += "SEC_DEFAULT_INTEGRITY = REQUIRED\n" 
        cfs += "ALLOW_WRITE = $(ALLOW_WRITE), submit-side@matchsession/*\n"         
        cfs += "ALLOW_ADMINISTRATOR = condor_pool@*/*\n"
        cfs += "NUM_SLOTS = 1\n"

        #cfs += "SEC_DEFAULT_AUTHENTICATION_METHODS = $(SEC_DEFAULT_AUTHENTICATION_METHODS), PASSWORD\n"  
        #cfs += "SEC_DEFAULT_AUTHENTICATION_METHODS = $(SEC_DEFAULT_AUTHENTICATION_METHODS), GSI\n"
        types = ' ,'.join(self.auth) 
        #cfs += "SEC_DEFAULT_AUTHENTICATION_METHODS = %s\n" % types

        if 'PASSWORD' in self.auth:
            self.log.info("Password auth requested...")
            cfs += "SEC_PASSWORD_FILE = $(RELEASE_DIR)/condor_password\n"
            cmd = "%s/sbin/condor_store_cred -f %s/condor_password -p %s" % (self.condor_dir,
                                                                     self.condor_dir, 
                                                                     self.passwdtoken)
            self.runcommand(cmd)
            self.log.info("Password file created successfully. ")
        if 'GSI' in self.auth:
            self.log.info("GSI auth requested...")
            cfs += "GSI_DAEMON_DIRECTORY=%s\n" % self.condor_dir         
            cfs += "GSI_DAEMON_TRUSTED_CA_DIR=/etc/grid-security/certificates\n" 
            cfs += "GSI_DAEMON_PROXY = %s\n" % os.environ['X509_USER_PROXY']                     

            #cfs += "GSI_DAEMON_NAME =%s\n" % self.authtok
            #self.log.debug("GSI_DAEMON_NAME=%s" % self.authtok )
            cfs += "GSI_DAEMON_NAME =%s\n" % self.gsitoken
            self.log.debug("GSI_DAEMON_NAME=%s" % self.gsitoken)

            cfs += "GRIDMAP = $(GSI_DAEMON_DIRECTORY)/grid-mapfile\n"         
            self.populate_gridmap()

        
        lc = open(lconfig, 'a')
        lc.write(cfs)
        lc.close()


    def run_condor_master(self):
        self.log.info("Running condor_master...")
        cmd = "%s/sbin/condor_master -f -pidfile %s/master.pid &" % ( self.condor_dir, self.condor_dir)
        self.log.debug("cmd = %s" % cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        masterpid = p.pid
        time.sleep(300)
        (out, err) = p.communicate()
        self.log.info("Condor_master has returned...")
        

    def cleanup(self):
        try:
            os.chdir(self.iwd)
            cd = self.condor_dir
            self.log.info("Removing temporary directory: %s" % cd)
            shutil.rmtree(cd)
            self.log.debug("Done remove temp dir.")            
        except Exception, ex:
            self.log.error("Exception caught during cleanup. Ex: %s" % ex)
            raise ex
    #
    # Utilities
    #
    def runcommand(self, cmd):
        self.log.debug("cmd = %s" % cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = p.communicate()
        if p.returncode == 0:
            self.log.info('Command return OK.')
            self.log.debug(out)
        else:
            self.log.error(err)
            raise Exception("External command failed. Job failed.") 
        return out

    def interrupt_handler(self, signal, frame):
        self.log.debug('Caught signal, running cleanup')
        self.cleanup()
        sys.exit()
        


###############################################################################
#                           M A I N                                           #
###############################################################################

if __name__ == '__main__':
    usage = """
    usage: $0 [options]

Run glidein against given collector:port and auth for at least -x seconds. 

OPTIONS:
    -h --help           Print help.
    -d --debug          Debug logging.      
    -v --verbose        Verbose logging. 
    -c --collector      Collector name
    -p --port           Collector port
    -a --authtype       Auth [password|gsi]
    -t --authtoken      Auth token (password or comma-separated subject DNs for GSI)
    -x --lingertime     Glidein linger time seconds [300]
    -n --noclean        Don't remove temp directory
"""
    
    # Defaults
    condor_version="8.5.6"
    condor_urlbase="http://download.virtualclusters.org/repository"
    collector_host="condor.grid.uchicago.edu"
    collector_port= "9618"

    authtype=["fs"]
    gsitoken="/DC=com/DC=DigiCert-Grid/O=Open Science Grid/OU=Services/CN=gridtest3.racf.bnl.gov, /DC=com/DC=DigiCert-Grid/O=Open Science Grid/OU=Services/CN=gridtest5.racf.bnl.gov "
    passwdtoken="changeme"

    lingertime="600"   # 10 minutes
    startexpression = "TRUE"
    loglevel=logging.DEBUG
    noclean=False
    
    # Handle command line options
    argv = sys.argv[1:]
    try:
        opts, args = getopt.getopt(argv, 
                                   "hdvc:p:a:t:x:r:u:n", 
                                   ["help",
                                    "debug",
                                    "verbose", 
                                    "collector=", 
                                    "port=", 

                                    "authtype=",
                                    #"authtoken=",
                                    "gsitoken=",
                                    "passwdtoken=",

                                    "lingertime=",
                                    "startexpression=",
                                    "condorversion=",
                                    "condorurlbase=",
                                    "noclean",
                                    ])
    except getopt.GetoptError, error:
        print( str(error))
        print( usage )                          
        sys.exit(1)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print(usage)                     
            sys.exit()            
        elif opt in ("-d", "--debug"):
            loglevel = logging.DEBUG
        elif opt in ("-v", "--verbose"):
            loglevel = logging.INFO
        elif opt in ("-c", "--collector"):
            collector_host = arg
        elif opt in ("-p", "--port"):
            collector_port = int(arg)

        elif opt in ("-a", "--authtype"):
            authtype = []
            for type in arg.split(','):
                type = type.strip()
                type = type.upper()
                authtype.append(type)
        #elif opt in ("-t", "--authtoken"):
        #    authtoken = arg
        elif opt in ("--gsitoken"):
            authtoken = arg
        elif opt in ("--passwdtoken"):
            authtoken = arg

        elif opt in ("-x","--lingertime"):
            lingertime = int(arg)
        elif opt in ("--startexpression"):
            startexpression = arg
        elif opt in ("-r", "--condorversion"):
            condor_version = arg
        elif opt in ("-u", "--condorurlbase"):
            condor_urlbase = arg
        elif opt in ("-n", "--noclean"):
            noclean = True
            
    try:
        gi = CondorGlidein(condor_version=condor_version, 
                   condor_urlbase=condor_urlbase,
                   collector=collector_host,
                   port=collector_port,

                   auth=authtype, 
                   #token=authtoken, 
                   gsitoken=gsitoken, 
                   passwdtoken=passwdtoken, 
                   
                   linger=lingertime, 
                   startexpression=startexpression,
                   loglevel=loglevel, 
                   noclean=noclean )
    except Exception, ex:
        #log.critical("Top-level exception: %s. Unable to create CondorGlidein object. Aborting." % ex)
        print("Top-level exception: %s. Unable to create CondorGlidein object. Aborting." % ex)
    else:
        signal.signal(signal.SIGINT, gi.interrupt_handler)
        gi.run_condor_master()
        gi.cleanup()
