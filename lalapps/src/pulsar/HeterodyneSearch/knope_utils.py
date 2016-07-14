"""
  Classes needed for the known pulsar search pipeline.

  (C) 2006, 2015 Matthew Pitkin

"""

# make print statements python 3-proof
from __future__ import print_function, division

__author__ = 'Matthew Pitkin <matthew.pitkin@ligo.org>'
__date__ = '$Date$'
__version__ = '$Revision$'

import string
import exceptions
import os
from glue import pipeline
import sys
import ast
import json
import subprocess as sp
import shutil
import uuid
import ConfigParser
import urlparse
from copy import deepcopy
import numpy as np
import pickle
from scipy import optimize

from lalapps import pulsarpputils as pppu


"""
Class for setting up the DAG for the whole known pulsar search pipeline
"""
class knopeDAG(pipeline.CondorDAG):
  def __init__(self, cp, configfilename, pulsarlist=None):
    """
    Initialise with ConfigParser cp object and the filename of the config file.

    If an error occurs the error_code variables will be set to -1. The value will stay as 0 on success.
    """

    self.error_code = 0 # set error_code to -1 following any failures
    self.config = cp
    if pulsarlist is not None:
      if isinstance(pulsarlist, list):
        self.pulsarlist = pulsarlist
      else:
        print("Error... 'pulsarlist' argument must be 'None' or a list.")
        self.error_code = 1
        return

    # if just re-doing post-processing try reading in previuos analysis pickle file
    self.postonly = self.get_config_option('analysis', 'postprocessing_only', cftype='boolean', default=False)
    prevdag = None
    if self.postonly:
      preprocessed_pickle = self.get_config_option('analysis', 'preprocessed_pickle_object')

      if preprocessed_pickle == None:
        print("Error... trying post-processing only, but no previous pickle file is given", file=sys.stderr)
        self.error_code = -1
        return
      else:
        try:
          fp = open(preprocessed_pickle, 'rb')
          prevdag = pickle.load(fp)
          fp.close()
        except:
          print("Error... trying post-processing only, but previous pickle file '%s' cannot be read in" % preprocessed_pickle, file=sys.stderr)
          self.error_code = -1
          return

    # Get run directory
    self.rundir = self.get_config_option('analysis', 'run_dir', cftype='dir', default=os.getcwd())
    if self.error_code != 0: return # quit class if there's been an error

    # a list of allowed IFO names
    allowed_ifos = ['H1', 'H2', 'L1', 'G1', 'V1', 'T1', 'K1']

    # Get the interferometers to analyse
    self.ifos = self.get_config_option('analysis', 'ifos', 'list')
    if self.error_code != 0: return # quit class if there's been an error

    # make sure ifo is an allowed value
    for ifo in self.ifos:
      if ifo not in allowed_ifos:
        print("Error... you have specified an unknown IFO '%s'" % ifo, file=sys.stderr)
        self.error_code = -1
        return

    if self.postonly: # check that this analysis uses the same, or a subset of, the previous IFOs
      for ifo in self.ifos:
        if ifo not in prevdag.ifos:
          print("Error... for 'post-processing-only' the current IFOs must be a subset of those in the previous run", file=sys.stderr)
          self.error_code = -1
          return

    # Get frequency factors (e.g. 1f and 2f) for analysis (default to twice the rotation frequency)
    self.freq_factors = self.get_config_option('analysis', 'freq_factors', cftype='list', default=[2.])
    if len(self.freq_factors) > 2: # cannot have more than two values
      print("Warning... only up to two frequency factors can be given. Defaulting to [2.]")
      self.freq_factors = [2.]
    if len(self.freq_factors) == 2: # if there are two values they must be 1 and 2
      if 1.0 not in self.freq_factors and 2.0 not in self.freq_factors:
        print("Warning... if giving two frequency factors they must be [1., 2.]. Defaulting to this")
        self.freq_factors = [1., 2.]
    for ff in self.freq_factors:
      if ff <= 0.:
        print("Warning... frequency factors cannot be negative. Defaulting to [2.]")
        self.freq_factors = [2.]

    if self.postonly: # check that this analysis uses the same, or a subset of, the previous frequency factors
      for ff in self.freq_factors:
        if ff not in prevdag.freq_factors:
          print("Error... for 'post-processing-only' the current frequency factors must be a subset of those in the previous run", file=sys.stderr)
          self.error_code = -1
          return

    # Get the base directory for the preprocessing analysis
    if not self.postonly:
      self.preprocessing_base_dir = self.get_config_option('analysis', 'preprocessing_base_dir', cftype='dict')
      if self.error_code != 0: return
    else:
      self.preprocessing_base_dir = prevdag.preprocessing_base_dir

    # try making directory/check if exists
    if not self.postonly:
      for ifo in self.ifos:
        self.mkdirs(self.preprocessing_base_dir[ifo])
        if self.error_code != 0: return

    # Get the start and end time of the analysis
    # see if starttime and endtime are integers or dictionaries
    self.starttime = self.get_config_option('analysis', 'starttime')
    if self.error_code != 0: return
    self.starttime = ast.literal_eval(self.starttime) # check if int or dict
    if isinstance(self.starttime, int): # convert to dictionary
      stdict = {}
      for ifo in self.ifos:
        stdict[ifo] = self.starttime
      self.starttime = stdict
    elif isinstance(self.starttime, dict): # check each detector has a start time
      for ifo in self.ifos:
        if ifo not in self.starttime:
          print("Error... 'starttime' either be a single 'int' value or a dictionary containing all detectors.", file=sys.stderr)
          self.error_code = -1
          return
    else:
      print("Error... 'starttime' either be a single 'int' value or a dictionary containing all detectors.", file=sys.stderr)
      self.error_code = -1
      return

    self.endtime = self.get_config_option('analysis', 'endtime')
    if self.error_code != 0: return
    self.endtime = ast.literal_eval(self.endtime) # check if int or dict
    if isinstance(self.endtime, int): # convert to dictionary
      etdict = {}
      for ifo in self.ifos:
        etdict[ifo] = self.endtime
      self.endtime = etdict
    elif isinstance(self.endtime, dict): # check each detector has an end time
      for ifo in self.ifos:
        if ifo not in self.endtime:
          print("Error... 'endtime' either be a single 'int' value or a dictionary containing all detectors.", file=sys.stderr)
          self.error_code = -1
          return
    else:
      print("Error... 'endtime' either be a single 'int' value or a dictionary containing all detectors.", file=sys.stderr)
      self.error_code = -1
      return

    # Get the pre-processing engine (heterodyne or SplInter - default to heterodyne)
    if not self.postonly:
      self.engine = self.get_config_option('analysis', 'preprocessing_engine', default='heterodyne')
      if self.error_code != 0: return

      if self.engine not in ['heterodyne', 'splinter']:
        print("Warning... 'preprocessing_engine' value '%s' not recognised. Defaulting to 'heterodyne'." % (self.engine))
      else:
        self.engine = 'heterodyne'
    else:
      self.engine = prevdag.engine

    # Get the solar system ephemeris path
    try:
      defaultephempath = os.environ['LALPULSAR_DATADIR']
    except:
      defaultephempath = None
    self.ephem_path = self.get_config_option('analysis', 'ephem_path', cftype='dir', default=defaultephempath)
    if self.error_code != 0: return

    # Get Condor accounting info (default to ligo.prod.o1.cw.targeted.bayesian)
    self.accounting_group = self.get_config_option('condor', 'accounting_group', default='ligo.prod.o1.cw.targeted.bayesian')
    if self.error_code != 0: return

    if 'cw.targeted.bayesian' not in self.accounting_group:
      print("Error... the 'accounting_group' should contain 'cw.targeted.bayesian'", file=sys.stderr)
      self.error_code = -1
      return

    if cp.has_option('condor', 'accounting_group_user'):
      self.accounting_group_user = cp.get('condor', 'accounting_group_user')

      if len(self.accounting_group_user) == 0:
        self.accounting_group_user = None # user not specified
    else:
      self.accounting_group_user = None # user not specified

    # Get the analysis run directory (where the DAG and sub files will be created and run from) (default to current working directory)
    self.run_dir = self.get_config_option('analysis', 'run_dir', default=os.getcwd())
    self.mkdirs(self.run_dir)
    if self.error_code != 0: return

    # Get the analysis log directory
    self.log_dir = self.get_config_option('analysis', 'log_dir')
    self.mkdirs(self.log_dir)
    if self.error_code != 0: return

    uniqueid = str(uuid.uuid4().hex)
    daglog = self.get_config_option('analysis', 'dag_name', default='knope-'+uniqueid+'.log')
    if len(daglog) == 0: # if no dag_name was given, but dag_name was still in .ini file
      daglog = 'known_pulsar_pipeline-'+uniqueid+'.log'
    self.daglogfile = os.path.join(self.log_dir, daglog)
    # initialise DAG
    pipeline.CondorDAG.__init__(self, self.daglogfile)

    # set dag file
    dagname = self.get_config_option('analysis', 'dag_name', default='knope-'+uniqueid)
    if len(dagname) == 0: # if no dag_name was given, but dag_name was stillin .ini file
      dagname = 'known_pulsar_pipeline-'+uniqueid
    self.set_dag_file(os.path.join(self.run_dir, dagname))

    # Check if running in autonomous mode
    self.autonomous = self.get_config_option('analysis', 'autonomous', cftype='boolean', default=False)
    if self.error_code != 0: return

    if self.autonomous:
      initialstart = self.get_config_option('analysis', 'autonomous_initial_start', cftype='int')
      if self.error_code != 0: return

      # convert to dictionary (to be consistent with start time)
      self.initial_start = {}
      for ifo in self.ifos:
        self.initial_start[ifo] = initialstart
    else:
      self.initial_start = self.starttime

    # Get pulsars to analyse (in the future this should be able to get pulsars from a database based on
    # certain parameters)
    self.pulsar_param_dir = self.get_config_option('analysis', 'pulsar_param_dir')
    if not os.path.isdir(self.pulsar_param_dir) and not os.path.isfile(self.pulsar_param_dir):
      print("Error... pulsar parameter file/directory '%s' does not exist!" % self.pulsar_param_dir, file=sys.stderr)
      self.error_code = -1
      return

    if self.postonly:
      if prevdag.pulsar_param_dir != self.pulsar_param_dir:
        print("Error... for 'post-processing-only' the pulsar parameter directory must be that same as in the previous run", file=sys.stderr)
        self.error_code = -1
        return

    self.unmodified_pulsars = [] # a list of pulsar .par files that have not been modified since the last run
    self.modified_pulsars = [] # a list of pulsar .par files that are new, or have been modified since the last run
    self.modification_files = [] # a list of dictionaries (one for each pulsar) containing the modification time file and modification time

    # Go through pulsar directory and check for any modified/new files
    if os.path.isdir(self.pulsar_param_dir):
      self.param_files = [os.path.join(self.pulsar_param_dir, pf) for pf in os.listdir(self.pulsar_param_dir) if '.par' in pf and os.path.isfile(os.path.join(self.pulsar_param_dir, pf)) and '.mod_' not in pf]

      if len(self.param_files) == 0:
        print("Error... no pulsar parameter files found in '%s'" % self.pulsar_param_dir, file=sys.stderr)
        self.error_code = -1
        return

      self.param_files.sort() # sort the files into alphabetical order
    elif os.path.isfile(self.pulsar_param_dir): # if a single file convert into list
      self.param_files = [self.pulsar_param_dir]
    else:
      print("Error... pulsar parameter file or directory '%s' does not exist" % self.pulsar_param_dir, file=sys.stderr)
      self.error_code = -1
      return

    self.analysed_pulsars = {} # dictionary keyed by PSRJ and containing the .par file path for all analysed pulsars
    self.skipped_pulsars = {}  # dictionary keyed on .par files for all skipped pulsars (including reason for exclusion)

    if not self.postonly:
      for par in self.param_files:
        # check that there is a PSRJ name in the .par file - if not then skip this pulsar
        # Get par file data
        try:
          psr = pppu.psr_par(par)
        except:
          print("Could not read in parameter file '%s'. Skipping this pulsar." % par)
          self.skipped_pulsars[par] = "Could not read in parameter file"
          continue

        #  check that there is a PSRJ name in the .par file (this is required)
        if 'PSRJ' not in psr.__dict__:
          print("Could not read 'PSRJ' value from '%s'. Skipping this pulsar." % par)
          self.skipped_pulsars[par] = "Could not read 'PSRJ' value"
          continue

        # check if we're just using selected input pulsars
        if pulsarlist is not None:
          if psr['PSRJ'] not in pulsarlist:
            continue

        # check that (if the pulsar is in a binary) it is an allowed binary type (given what's coded in lalpulsar)
        if 'BINARY' in psr.__dict__:
          bintype = psr['BINARY']
          if bintype not in ['BT', 'BT1P', 'BT2P', 'BTX', 'ELL1', 'DD', 'DDS', 'MSS', 'T2']:
            print("Binary type '%s' in '%s' is not recognised. Skipping this pulsar." % (bintype, par))
            self.skipped_pulsars[par] = "Binary type '%s' is currenlty not recognised" % bintype
            continue

        # check that .par file contains ephemeris information and units (if not present defaults will be used - see get_ephemeris)
        if psr['EPHEM'] != None:
          if psr['EPHEM'] not in ['DE200', 'DE405', 'DE414', 'DE421']:
            print("Unregconised ephemeris '%s' in '%s'. Skipping this source" % (psr['EPHEM'], par))
            self.skipped_pulsars[par] = "Unregconised ephemeris '%s'" % psr['EPHEM']
            continue

        if psr['UNITS'] != None:
          if psr['UNITS'] not in ['TCB', 'TDB']:
            print("Unregconised time units '%s' in '%s'. Skipping this source" % (psr['UNITS'], par))
            self.skipped_pulsars[par] = "Unregconised ephemeris '%s'" % psr['UNITS']
            continue

        self.analysed_pulsars[psr['PSRJ']] = par

        # create parfile modification time file
        modtimefile = os.path.join(os.path.dirname(par), '.mod_'+os.path.basename(par))

        # Check if modification time file exists
        if not os.path.isfile(modtimefile):
          # add par file to modified pulsars list
          self.modified_pulsars.append(par)

          # create modification time file
          modtime = os.stat(par).st_mtime
          self.modification_files.append({'file': modtimefile, 'time': str(modtime)})
        else: # check whether par file modification time is consistent with value in modtimefile
          parmodtime = str(os.stat(par).st_mtime)
          fm = open(modtimefile, 'r')
          try:
            oldmodtime = fm.readline().strip()
          except:
            print("Warning... could not read modification time from '%s'. Assuming file is modified" % modtimefile)
            oldmodtime = -1.23456789
          fm.close()

          if parmodtime == oldmodtime: # file is unmodified
            self.unmodified_pulsars.append(par)
          else: # file is modified
            self.modification_files.append({'file': modtimefile, 'time': parmodtime}) # update the time in the .mod file
            self.modified_pulsars.append(par)

      if pulsarlist is not None:
        if len(self.analysed_pulsars) == 0:
          print("Could not find any of the listed pulsars '[%s]' in the .par file directory '%s'." % (', '.join(pulsarlist), self.pulsar_param_dir))
          self.error_code = 1
          return

    self.segment_file_update = [] # to contain a list of pairs of segment files - the former to be concatenated into the latter if required

    if not self.postonly:
      # Setup pre-processing jobs (datafind, segment finding and heterodyne/splinter running) for each pulsar
      self.setup_preprocessing()
      if self.error_code != 0: return

      # Check whether only the preprocessing (heterodyne or splinter) jobs are required
      self.preprocessing_only = self.get_config_option('analysis', 'preprocessing_only', cftype='boolean', default=False)
      if self.error_code != 0: return
    else:
      # use information from previous run
      self.preprocessing_only = False
      self.remove_job = None
      if pulsarlist is None:
        self.unmodified_pulsars = prevdag.unmodified_pulsars
        self.modified_pulsars = prevdag.modified_pulsars
        self.analysed_pulsars = prevdag.analysed_pulsars
        self.skipped_pulsars = prevdag.skipped_pulsars
        self.processed_files = prevdag.processed_files
      else: # if analysing only selected pulsars (from pulsarlist) just get information on them
        for psrl in pulsarlist:
          if psrl not in prevdag.analysed_pulsars:
            print("Error... specified pulsar '%s' could not be found in previous run pickle file '%s'." % (psrl, preprocessed_pickle))
            self.error_code = 1
            return

          if psrl in prevdag.unmodified_pulsars:
            self.unmodified_pulsars[psrl] = prevdag.unmodified_pulsars[psrl]
          if psrl in prevdag.modified_pulsars:
            self.modified_pulsars[psrl] = prevdag.modified_pulsars[psrl]

          self.analysed_pulsars[psrl] = prevdag.analysed_pulsars[psrl]
          self.processed_files = {}
          self.processed_files[psrl] = prevdag.processed_files[psrl]

    if self.preprocessing_only: # end class initialisation
      # output par file modification times (do this now, so that modification files are overwritten if the script had failed earlier)
      for pitem in self.modification_files:
        fm = open(pitem['file'], 'w')
        fm.write(pitem['time'])
        fm.close()

      # output ammended segment list files
      for sfs in self.segment_file_update:
        p = sp.Popen("cat " + sfs[0] + " >> " + sfs[1], shell=True)
        p.communicate()
        if p.returncode != 0:
          print("Warning... could not append segments to previous segments file. No log of previous segments will be available.")
      return

    # setup parameter estimation
    self.setup_parameter_estimation()
    if self.error_code != 0: return

    # setup post-processing page creation
    self.setup_results_pages()

    ### FINAL CLOSE OUT ITEMS

    # output par file modification times (do this now, so that modification files are overwritten if the script had failed earlier)
    for pitem in self.modification_files:
      fm = open(pitem['file'], 'w')
      fm.write(pitem['time'])
      fm.close()

    # output ammended segment list files
    for sfs in self.segment_file_update:
      p = sp.Popen("cat " + sfs[0] + " >> " + sfs[1], shell=True)
      p.communicate()
      if p.returncode != 0:
        print("Warning... could not append segments to previous segments file. No log of previous segments will be available.")

    # output dictionaries of analysed pulsars and skipped pulsars to JSON files
    fpa = open(os.path.join(self.run_dir, 'analysed_pulsars.txt'), 'w')
    json.dump(self.analysed_pulsars, fpa, indent=2)
    fpa.close()

    fps = open(os.path.join(self.run_dir, 'skipped_pulsars.txt'), 'w')
    json.dump(self.skipped_pulsars, fps, indent=2)
    fps.close()

    # email notification that the analysis has finished if required
    email = self.get_config_option('analysis', 'email')
    if email != None:
      if '@' not in email:
        print("Warning... email address '%s' is invalid. No notification will be sent." % email)
      else:
        import smtplib
        import socket

        # try setting email server
        try:
          # set up sender
          try:
            HOST = socket.getfqdn()
            USER = os.environ['USER']
            FROM = USER+'@'+HOST
          except: # default from to 'matthew.pitkin@ligo.org'
            FROM = 'matthew.pitkin@ligo.org'

          subject = "lalapps_knope: successful setup"
          messagetxt = "Hi User,\n\nYour analysis using configuration file '%s' has successfully setup the analysis. Once complete the results will be found at %s.\n\nRegards lalapps_knope\n" % (configfilename, self.results_url)

          emailtemplate = "From: {0}\nTo: {1}\nSubject: {2}\n\n{3}"
          message = emailtemplate.format(FROM, email, subject, messagetxt)
          server = smtplib.SMTP('localhost')
          server.sendmail(FROM, email, message)
          server.quit()
        except:
          print("Warning... could not send notification email.")


  def setup_results_pages(self):
    """
    Setup the results webpage creation
    """

    # get directory for output results
    self.results_basedir = self.get_config_option('results_page', 'web_dir')
    self.results_pulsar_dir = {} # dictionary of results directories for individual pulsars
    self.results_pulsar_ini = {} # dictionary of results configuration files for individual pulsars
    self.results_pulsar_url = {} # dictionary of results page URLs
    self.mkdirs(self.results_basedir)
    if self.error_code != 0: return

    # get URL for output results
    self.results_url = self.get_config_option('results_page', 'base_url')

    # run individual pulsar results page creation
    self.results_exec = self.get_config_option('results_page', 'results_exec', default='/usr/bin/lalapps_knope_result_page')
    self.results_universe = self.get_config_option('results_page', 'universe', default='local')

    # check file exists and is executable
    if not os.path.isfile(self.results_exec) or not os.access(self.results_exec, os.X_OK):
      print("Warning... 'results_exec' in '[results_page]' does not exist or is not an executable. Try finding code in path.")
      resultexec = self.find_exec_file('lalapps_knope_result_page')

      if resultexec == None:
        print("Error... could not find 'lalapps_knope_result_page' in 'PATH'", file=sys.stderr)
        self.error_code = -1
        return
      else:
        self.results_exec = resultexec

    self.collate_exec = self.get_config_option('results_page', 'collate_exec', default='/usr/bin/lalapps_knope_collate_results')

    # check file exists and is executable
    if not os.path.isfile(self.collate_exec) or not os.access(self.collate_exec, os.X_OK):
      print("Warning... 'collate_exec' in '[results_page]' does not exist or is not an executable. Try finding code in path.")
      collateexec = self.find_exec_file('lalapps_knope_collate_results')

      if collateexec == None:
        print("Error... could not find 'lalapps_knope_collate_results' in 'PATH'", file=sys.stderr)
        self.error_code = -1
        return
      else:
        self.collate_exec = collateexec

    # check if running on an injection
    self.injection = self.get_config_option('analysis', 'injections', cftype='boolean', default=False)
    self.use_gw_phase = self.get_config_option('pe', 'use_gw_phase', cftype='boolean', default=False)
    if self.error_code != 0: return

    # check upper limit credible interval to use
    self.upper_limit = self.get_config_option('results_page', 'upper_limit', cftype='int', default=95)

    # check whether to show joint posterior plot for all parameters
    self.show_all_posteriors = self.get_config_option('results_page', 'show_all_posteriors', cftype='boolean', default=False)

    # create parameter estimation job
    resultpagejob = resultpageJob(self.results_exec, univ=self.results_universe, accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir)
    collatejob = collateJob(self.collate_exec, univ=self.results_universe, accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir)
    collatenode = collateNode(collatejob)

    # loop through pulsars
    for pname in self.analysed_pulsars:
      # create results directory for pulsar
      self.results_pulsar_dir[pname] = os.path.join(self.results_basedir, pname)
      self.results_pulsar_url[pname] = urlparse.urljoin(self.results_url, pname)

      self.mkdirs(self.results_pulsar_dir[pname])
      if self.error_code != 0: return

      cp = ConfigParser.ConfigParser() # create config parser to output .ini file
      # create configuration .ini file
      inifile = os.path.join(self.results_pulsar_dir[pname], pname+'.ini')

      # add sections
      cp.add_section('general')
      cp.add_section('parameter_estimation')
      cp.add_section('data')
      cp.add_section('output')
      cp.add_section('plotting')

      cp.set('output', 'path', self.results_pulsar_dir[pname]) # set output directory
      cp.set('output', 'indexpage', os.path.relpath(self.results_basedir, self.results_pulsar_dir[pname]))

      cp.set('general', 'parfile', self.analysed_pulsars[pname]) # set the pulsar parameter file
      cp.set('general', 'detectors', self.ifos)                  # set the detectors
      cp.set('general', 'upper_limit', self.upper_limit)         # set the upper limit credible interval

      if self.pe_coherent_only:
        cp.set('general', 'joint_only', True) # only output the joint multi-detector analysis
      else:
        cp.set('general', 'joint_only', False)

      if self.pe_incoherent_only:
        cp.set('general', 'with_joint', False)  # only output individual detector analyses
      else:
        cp.set('general', 'with_joint', True)   # include joint multi-detector analysis

      if self.pe_num_background > 0:
        cp.set('general', 'with_background', True)  # include background analysis
      else:
        cp.set('general', 'with_background', False) # no background analysis present

      if self.injection:
        cp.set('general', 'injection', True) # set if an injection or not
      else:
        cp.set('general', 'injection', False)

      if self.use_gw_phase:
        cp.set('general', 'use_gw_phase', True) # use GW initial phase (rather than rotational phase) e.g. for hardware injections
      else:
        cp.set('general', 'use_gw_phase', False)

      cp.set('general', 'harmonics', self.freq_factors)   # set frequency harmonics in analysis
      cp.set('general', 'model_type', self.pe_model_type) # set 'waveform' or 'source' model type
      cp.set('general', 'biaxial', self.pe_biaxial)       # set if using a biaxial source model

      # get posterior files (and background directories)
      posteriorsfiles = {}
      backgrounddir = {}
      for i, comb in enumerate(self.pe_combinations):
        dets = comb['detectors']
        detprefix = comb['prefix']

        if len(dets) == 1:
          det = dets[0]
        else:
          det = 'Joint' # use 'Joint' as the term for a multi-detector analysis

        posteriorsfiles[det] = os.path.join(self.pe_posterior_basedir, pname)
        posteriorsfiles[det] = os.path.join(posteriorsfiles[det], detprefix)

        if self.pe_num_background > 0:
          backgrounddir[det] = os.path.join(self.pe_posterior_background_basedir, pname)
          backgrounddir[det] = os.path.join(backgrounddir[det], detprefix)

        dirpostfix = ''
        if len(self.freq_factors) > 1: # coherent multi-frequency analysis
          dirpostfix = 'multiharmonic'
        else:
          if not self.freq_factors[0]%1.: # for integers just output directory as e.g. 2f
            dirpostfix = '%df' % int(self.freq_factors[0])
          else:
            dirpostfix = '%.2ff' % self.freq_factors[0]

        posteriorsfiles[det] = os.path.join(posteriorsfiles[det], dirpostfix)
        posteriorsfiles[det] = os.path.join(posteriorsfiles[det], 'posterior_samples_%s.hdf' % pname)
        if self.pe_num_background > 0: backgrounddir[det] = os.path.join(backgrounddir[det], dirpostfix)

      cp.set('parameter_estimation', 'posteriors', posteriorsfiles)

      if self.pe_num_background > 0:
        cp.set('parameter_estimation', 'background', backgrounddir)

      datafiles = {}
      for ifo in self.ifos:
        if len(self.freq_factors) > 1:
          filelist = []
          for ff in self.freq_factors:
            filelist.append(self.processed_files[pname][ifo][ff][-1])
        else:
          filelist = self.processed_files[pname][ifo][self.freq_factors[0]][-1]
        datafiles[ifo] = filelist

      cp.set('data', 'files', datafiles)

      cp.set('plotting', 'all_posteriors', self.show_all_posteriors)

      # output configuration file
      try:
        fp = open(inifile, 'w')
        cp.write(fp)
        fp.close()
      except:
        print("Error... could not write configuration file '%s' for results page" % inifile, file=sys.stderr)
        self.error_code = -1
        return

      # create dag node
      resultsnode = resultpageNode(resultpagejob)
      resultsnode.set_config(inifile)

      # add parent lalapps_nest2pos job
      for n2pnode in self.pe_nest2pos_nodes[pname]:
        resultsnode.add_parent(n2pnode)

      if self.pe_num_background > 0:
        for n2pnode in self.pe_nest2pos_background_nodes[pname]:
          resultsnode.add_parent(n2pnode)

      self.add_node(resultsnode)

      # add as parent to the collation node
      collatenode.add_parent(resultsnode)

    # collate results into a results table
    cpc = ConfigParser.ConfigParser() # create config parser to output .ini file
    # create configuration .ini file
    cinifile = os.path.join(self.results_basedir, 'collate.ini')

    # create sections
    cpc.add_section('output')
    cpc.add_section('input')
    cpc.add_section('general')

    cpc.set('output', 'path', self.results_basedir) # set output directory
    cpc.set('input', 'path', self.results_basedir)  # set directory containing individual results directories

    # get sort type and direction
    sorttype = self.get_config_option('results_page', 'sort_value', default='name') # default sorting on name
    cpc.set('general', 'sort_value', sorttype)
    sortdirection = self.get_config_option('results_page', 'sort_direction', default='ascending') # default sorting in ascending order
    cpc.set('general', 'sort_direction', sortdirection)
    if self.pe_coherent_only:
      cpc.set('general', 'detectors', ['Joint'])
    elif self.pe_incoherent_only:
      cpc.set('general', 'detectors', self.ifos)
    else:
      cdets = deepcopy(self.ifos)
      cdets.append('Joint')
      cpc.set('general', 'detectors', cdets)

    # get pulsar parameters to output
    paramout = self.get_config_option('results_page', 'parameters', cftype='list', default=['f0'])
    cpc.set('general', 'parameters', paramout)

    # get results to output
    resout = self.get_config_option('results_page', 'results', cftype='list', default=['h0ul'])
    cpc.set('general', 'results', resout)

    # write and set ini file
    try:
      fp = open(cinifile, 'w')
      cpc.write(fp)
      fp.close()
    except:
      print("Error... could not write configuration file '%s' for results collation page" % cinifile, file=sys.stderr)
      self.error_code = -1
      return

    collatenode.set_config(cinifile)

    self.add_node(collatenode)


  def setup_preprocessing(self):
    """
    Setup the preprocessing analysis: data finding, segment finding and heterodyne/splinter data processing
    """

    # set the data find job and nodes
    self.setup_datafind()
    if self.error_code != 0: return

    # loop through the pulsars and setup required jobs for each
    if self.engine == 'heterodyne':
      self.setup_heterodyne()
      if self.error_code != 0: return

    if self.engine == 'splinter':
      self.setup_splinter()
      if self.error_code != 0: return

    # create jobs to concatenate output fine heterodyned/Splinter files if required
    self.remove_job = None
    self.concatenate_files()
    if self.error_code != 0: return


  def setup_parameter_estimation(self):
    """
    Setup parameter estimation jobs/nodes for signal and background analyses
    """

    # get executable
    self.pe_exec = self.get_config_option('pe', 'pe_exec', default='lalapps_pulsar_parameter_estimation_nested')
    if self.error_code != 0: return

    # check file exists and is executable
    if not os.path.isfile(self.pe_exec) or not os.access(self.pe_exec, os.X_OK):
      print("Warning... 'pe_exec' in '[pe]' does not exist or is not an executable. Try finding code in path.")
      peexec = self.find_exec_file('lalapps_pulsar_parameter_estimation_nested')

      if peexec == None:
        print("Error... could not find 'lalapps_pulsar_parameter_estimation_nested' in 'PATH'", file=sys.stderr)
        self.error_code = -1
        return
      else:
        self.pe_exec = peexec

    # Get Condor universe (default to vanilla)
    self.pe_universe = self.get_config_option('pe', 'universe', default='vanilla')
    if self.error_code != 0: return

    self.pe_nest2pos_nodes = {} # condor nodes for the lalapps_nest2pos jobs (needed to use as parents for results processing jobs)
    self.pe_nest2pos_background_nodes = {} # nodes for background analysis

    # see whether to run just as independent detectors, or independently AND coherently over all detectors
    if len(self.ifos) == 1:
      self.pe_incoherent_only = True # set to True for one detector
    else:
      self.pe_incoherent_only = self.get_config_option('analysis', 'incoherent_only', cftype='boolean', default=False)

    # see whether to run only the coherent multidetector analysis analysis
    self.pe_coherent_only = False
    if len(self.ifos) > 1:
      self.pe_coherent_only = self.get_config_option('analysis', 'coherent_only', cftype='boolean', default=False)

    # get the number of background analyses to perform
    self.pe_num_background = self.get_config_option('analysis', 'num_background', cftype='int', default=0)
    if self.pe_num_background < 0:
      print("Warning... 'num_background' is a negative value. Defaulting to zero background runs")
      self.pe_num_background = 0

    # get the PE output directory
    self.pe_output_basedir = self.get_config_option('pe', 'pe_output_dir', cftype='dir')

    # Make directory
    self.mkdirs(self.pe_output_basedir)
    if self.error_code != 0: return

    # set background run directories if required
    self.pe_output_background_basedir = self.get_config_option('pe', 'pe_output_dir_background', cftype='dir')
    if self.pe_num_background != 0:
      if self.pe_output_background_basedir == None:
        print("Error... no background analysis directory has been set", file=sys.stderr)
        self.error_code = -1;
        return
      else:
        self.mkdirs(self.pe_output_background_basedir)
        if self.error_code != 0: return

    # get some general PE parameters
    self.pe_nlive = self.get_config_option('pe', 'n_live', cftype='int', default=2048)              # number of live points
    self.pe_nruns = self.get_config_option('pe', 'n_runs', cftype='int', default=1)                 # number of parallel runs
    self.pe_tolerance = self.get_config_option('pe', 'tolerance', cftype='float', default=0.1)      # nested sampling stopping criterion
    self.pe_random_seed = self.get_config_option('pe', 'random_seed', cftype='int', allownone=True) # random number generator seed
    self.pe_nmcmc = self.get_config_option('pe', 'n_mcmc', cftype='int', allownone=True)            # number of MCMC steps for each nested sample
    self.pe_nmcmc_initial = self.get_config_option('pe', 'n_mcmc_initial', cftype='int', default=500)
    self.pe_non_gr = self.get_config_option('pe', 'non_gr', cftype='boolean', default=False)        # use non-GR parameterisation (default to False)

    # parameters for background runs
    self.pe_nruns_background = self.get_config_option('pe', 'n_runs_background', cftype='int', default=1)
    self.pe_nlive_background = self.get_config_option('pe', 'n_live_background', cftype='int', default=1024)

    # parameters for ROQ
    self.pe_roq = self.get_config_option('pe', 'use_roq', cftype='boolean', default=False)                # check if using Reduced Order Quadrature (ROQ)
    self.pe_roq_ntraining = self.get_config_option('pe', 'roq_ntraining', cftype='int', default=2500)     # number of training waveforms for reduced basis generation
    self.pe_roq_tolerance = self.get_config_option('pe', 'roq_tolerance', cftype='float', default=5e-12)  # mis-match tolerance when producing reduced basis
    self.pe_roq_uniform = self.get_config_option('pe', 'roq_uniform', cftype='boolean', default=False)        # check if setting uniform distributions for sprinkling traning waveform parameters
    self.pe_roq_chunkmax = self.get_config_option('pe', 'roq_chunkmax', cftype='int', default=1440)       # maximum data chunk length for creating ROQ

    # FIXME: Currently this won't run with non-GR parameters, so output a warning and default back to GR!
    if self.pe_non_gr:
      print("Warning... currently this will not run with non-GR parameters. Reverting to GR-mode.")
      self.pe_non_gr = False

    # if searching at both the rotation frequency and twice rotation frequency set which parameterisation to use
    self.pe_model_type = self.get_config_option('pe', 'model_type', default='waveform')
    if self.pe_model_type not in ['waveform', 'source']:
      print("Warning... the given 'model_type' '%s' is not allowed. Defaulting to 'waveform'" % self.pe_model_type)
      self.pe_model_type = 'waveform'

    self.pe_biaxial = False
    # check whether using a biaxial signal
    if len(self.freq_factors) == 2 and self.pe_non_gr == False:
      self.pe_biaxial = self.get_config_option('pe', 'biaxial', cftype='boolean', default=False) # use a biaxial signal model

    # check whether using the Student's t-likelihood or Gaussian likelihood
    self.pe_gaussian_like = self.get_config_option('pe', 'gaussian_like', cftype='boolean', default=False)
    if self.engine == 'splinter': # always use the Gaussian likelihood for the SplInter processed data
      self.pe_gaussian_like = True

    # check if there is a pre-made prior file to use for all pulsars
    self.pe_prior_options = self.get_config_option('pe', 'prior_options', cftype='dict')
    self.pe_premade_prior_file = self.get_config_option('pe', 'premade_prior_file', allownone=True)

    if self.pe_premade_prior_file != None:
      if not os.path.isfile(self.pe_premade_prior_file):
        print("Error... pre-made prior file '%s' does not exist!" % self.pe_premade_prior_file, file=sys.stderr)
        self.error_code = -1
        return

    self.pe_derive_amplitude_prior = self.get_config_option('pe', 'derive_amplitude_prior', cftype='boolean', default=False)

    if self.pe_derive_amplitude_prior:
      # get JSON file containing any previous amplitude upper limits for pulsars
      self.pe_amplitude_prior_file = self.get_config_option('pe', 'amplitude_prior_file', allownone=True)

      self.pe_prior_info = None
      self.pe_prior_asds = {}

      # get file, or dictionary of amplitude spectral density files (e.g. from a previous run) to derive amplitude priors
      try:
        self.pe_amplitude_prior_asds = ast.literal_eval(self.get_config_option('pe', 'amplitude_prior_asds', allownone=True))
      except:
        self.pe_amplitude_prior_asds = self.get_config_option('pe', 'amplitude_prior_asds', allownone=True)

      try:
        self.pe_amplitude_prior_obstimes = ast.literal_eval(self.get_config_option('pe', 'amplitude_prior_obstimes', allownone=True))
      except:
        self.pe_amplitude_prior_obstimes = self.get_config_option('pe', 'amplitude_prior_obstimes', allownone=True)

      self.pe_amplitude_prior_type = self.get_config_option('pe', 'amplitude_prior_type', default='fermidirac')

    # check if using par files errors in parameter estimation
    self.pe_use_parameter_errors = self.get_config_option('pe', 'use_parameter_errors', cftype='boolean', default=False)

    # check for executable for merging nested sample files/converting them to posteriors
    self.pe_n2p_exec = self.get_config_option('pe', 'n2p_exec', default='lalapps_nest2pos')
    if self.error_code != 0: return

    # check file exists and is executable
    if not os.path.isfile(self.pe_n2p_exec) or not os.access(self.pe_n2p_exec, os.X_OK):
      print("Warning... 'pe_n2p_exec' in '[pe]' does not exist or is not an executable. Try finding code in path.")
      pen2pexec = self.find_exec_file('lalapps_nest2pos')

      if pen2pexec == None:
        print("Error... could not find 'lalapps_nest2pos' in 'PATH'", file=sys.stderr)
        self.error_code = -1
        return
      else:
        self.pe_n2p_exec = pen2pexec

    self.pe_posterior_basedir = self.get_config_option('pe', 'n2p_output_dir')
    if self.pe_posterior_basedir == None:
      print("Error... no 'n2p_output_dir' specified in '[pe]' giving path for posterior sample outputs", file=sys.stderr)
      self.error_code = -1
      return
    self.mkdirs(self.pe_posterior_basedir)
    if self.error_code != 0: return

    if self.pe_num_background > 0:
      self.pe_posterior_background_basedir = self.get_config_option('pe', 'n2p_output_dir_background')
      if self.pe_posterior_background_basedir == None:
        print("Error... no 'n2p_output_dir_background' specified in '[pe]' giving path for posterior sample outputs", file=sys.stderr)
        self.error_code = -1
        return
      self.mkdirs(self.pe_posterior_background_basedir)
      if self.error_code != 0: return

    # check whether to remove all the nested sample files after the run
    self.pe_clean_nest_samples = self.get_config_option('pe', 'clean_nest_samples', cftype='boolean', default=False)

    # create parameter estimation job
    pejob = ppeJob(self.pe_exec, univ=self.pe_universe, accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir)

    # create job to merge nested samples and convert to posterior samples
    n2pjob = nest2posJob(self.pe_n2p_exec, univ='local', accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir)

    # create job for moving SNR files
    mvjob = moveJob(accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir)

    # create job for removing nested samples (use previous remove job if existing)
    if self.remove_job == None:
      rmjob = removeJob(accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir)
    else:
      rmjob = self.remove_job

    # work out combinations of parameter estimation jobs to run (FIXME: if non-GR mode was able to be enabled then another
    # combination would include those below, but in both GR and non-GR flavours)
    # NOTE: if running with two frequency factors (which have been fixed, so they can only be 1f and 2f), this just runs
    # for a multi-harmonic search at both frequencies. If you want to run at a single frequency then that should be set up
    # independently.
    self.pe_combinations = []
    for ifo in self.ifos:
      if not self.pe_coherent_only:
        self.pe_combinations.append({'detectors': [ifo], 'prefix': ifo}) # all individual detector runs

    if not self.pe_incoherent_only:
      self.pe_combinations.append({'detectors': self.ifos, 'prefix': "".join(self.ifos)}) # add joint multi-detector run

    self.pe_prior_files = {} # dictionary to contain prior files for each pulsar
    self.pe_cor_files = {}   # dictionary to contain correlation coefficient matrices for pulsars as required

    # dictionary of nest2pos nodes
    n2pnodes = {}

    # loop over the total number of jobs (single signal job and background jobs)
    njobs = self.pe_num_background + 1
    for j in range(njobs):
      # loop through each pulsar that has been analysed
      for pname in self.analysed_pulsars:
        psr = pppu.psr_par(self.analysed_pulsars[pname])

        # directories for output nested sample files
        if j == 0: # first iteration of outer loop is the signal job
          psrdir = os.path.join(self.pe_output_basedir, pname)
        else: # subsequent iterations are for background jobs
          psrdir = os.path.join(self.pe_output_background_basedir, pname)

        # directories for output posterior files
        if j == 0: # first iteration of outer loop is the signal job
          psrpostdir = os.path.join(self.pe_posterior_basedir, pname)
        else: # subsequent iterations are for background jobs
          psrpostdir = os.path.join(self.pe_posterior_background_basedir, pname)

        if self.pe_roq:
          nroqruns = 1 # add one run for the ROQ weights calculation
        else:
          nroqruns = 0

        # create directory for that pulsar
        self.mkdirs(psrdir)
        if self.error_code != 0: return

        self.mkdirs(psrpostdir)
        if self.error_code != 0: return

        n2pnodes[pname] = [] # list of nodes for lalapps_nest2pos jobs for a given pulsar

        for comb in self.pe_combinations:
          dets = comb['detectors']
          detprefix = comb['prefix']

          # set up directories for detectors
          detdir = os.path.join(psrdir, detprefix)
          self.mkdirs(detdir)
          if self.error_code != 0: return

          detpostdir = os.path.join(psrpostdir, detprefix)
          self.mkdirs(detpostdir)
          if self.error_code != 0: return

          # make directories for frequency factors
          if len(self.freq_factors) > 1: # coherent multi-frequency analysis
            ffdir = os.path.join(detdir, 'multiharmonic')
            ffpostdir = os.path.join(detpostdir, 'multiharmonic')
          else:
            if not self.freq_factors[0]%1.: # for integers just output directory as e.g. 2f
              ffdir = os.path.join(detdir, '%df' % int(self.freq_factors[0]))
              ffpostdir = os.path.join(detpostdir, '%df' % int(self.freq_factors[0]))
            else:
              ffdir = os.path.join(detdir, '%.2ff' % self.freq_factors[0])
              ffpostdir = os.path.join(detpostdir, '%.2ff' % self.freq_factors[0])

          # add integer numbering to directories if running background analysis jobs
          if j > 0:
            ffdir = os.path.join(ffdir, '%05d' % (j-1)) # start directory names as 00000, 00001, 00002, etc
            ffpostdir = os.path.join(ffpostdir, '%05d' % (j-1))

          self.mkdirs(ffdir)
          if self.error_code != 0: return

          self.mkdirs(ffpostdir)
          if self.error_code != 0: return

          randomiseseed = ''
          if j == 0:
            # create prior file for analysis (use this same file for all background runs)
            priorfile = self.create_prior_file(psr, psrdir, dets, self.freq_factors, ffdir)

            nruns = self.pe_nruns
            nlive = self.pe_nlive
          else:
            nruns = self.pe_nruns_background
            nlive = self.pe_nlive_background
            # set seed for randomising data (this needs to be the same over each nruns)
            randomiseseed = ''.join([str(f) for f in np.random.randint(1, 10, size=15).tolist()])

          # set output ROQ weights file
          if self.pe_roq:
            roqweightsfile = os.path.join(ffdir, 'roqweights.bin')

          nestfiles = [] # list of nested sample file names
          penodes = []
          roqinputnode = None

          # setup job(s)
          i = counter = 0
          while counter < nruns+nroqruns: # loop over the required number of runs
            penode = ppeNode(pejob)
            if self.pe_random_seed != None:
              penode.set_randomseed(self.pe_random_seed)      # set seed for RNG
            penode.set_detectors(','.join(dets))              # add detectors
            penode.set_par_file(self.analysed_pulsars[pname]) # add parameter file
            if pname in self.pe_cor_files:
              penode.set_cor_file(self.pe_cor_files[pname])   # set parameter correlation coefficient file
            penode.set_prior_file(priorfile)                  # set prior file
            penode.set_harmonics(','.join([str(ffv) for ffv in self.freq_factors])) # set frequency harmonics

            penode.set_Nlive(nlive)                           # set number of live points
            if self.pe_nmcmc != None:
              penode.set_Nmcmc(self.pe_nmcmc)                 # set number of MCMC iterations for choosing new points
            penode.set_Nmcmcinitial(self.pe_nmcmc_initial)    # set initial number of MCMC interations for reampling the prior
            penode.set_tolerance(self.pe_tolerance)           # set tolerance for ending nested sampling

            # set the output nested samples file
            nestfiles.append(os.path.join(ffdir, 'nested_samples_%s_%05d.hdf' % (pname, i)))
            penode.set_outfile(nestfiles[i])

            if self.pe_roq:
              penode.set_roq()
              penode.set_roq_chunkmax(str(self.pe_roq_chunkmax))

              if counter == 0: # first time round just output weights
                penode.set_roq_ntraining(str(self.pe_roq_ntraining))
                penode.set_roq_tolerance(str(self.pe_roq_tolerance))
                penode.set_roq_outputweights(roqweightsfile)
                if self.pe_roq_uniform:
                  penode.set_roq_uniform()
              else: # use pre-created weights file
                penode.set_roq_inputweights(roqweightsfile)

            # for background runs set the randomise seed
            if j > 0:
              penode.set_randomise(randomiseseed)

            # add input files
            inputfiles = []
            for det in dets:
              for ff in self.freq_factors:
                inputfiles.append(self.processed_files[pname][det][ff][-1])
            penode.set_input_files(','.join(inputfiles))

            if self.pe_gaussian_like or self.engine == 'splinter':
              # use Gaussian likelihood
              penode.set_gaussian_like()

            if (len(self.freq_factors) == 2 and 1. in self.freq_factors and 2. in self.freq_factors):
              # set whether using source model
              if self.pe_model_type == 'source':
                penode.set_source_model()

              # set whether using a biaxial signal
              if self.pe_biaxial:
                penode.set_biaxial()

            # set Earth, Sun and time ephemeris files
            if psr['EPHEM'] != None and self.ephem_path != None:
              earthfile = os.path.join(self.ephem_path, 'earth00-19-%s.dat.gz' % psr['EPHEM'])
              penode.set_ephem_earth(earthfile)
              sunfile = os.path.join(self.ephem_path, 'sun00-19-%s.dat.gz' % psr['EPHEM'])
              penode.set_ephem_sun(sunfile)

            if psr['UNITS'] != None and self.ephem_path != None:
              if psr['UNITS'] == 'TDB':
                timefile = os.path.join(self.ephem_path, 'tdb_2000-2019.dat.gz')
              else:
                timefile = os.path.join(self.ephem_path, 'te405_2000-2019.dat.gz')
              penode.set_ephem_time(timefile)

            # add parents (unless just doing post-processing)
            if not self.postonly:
              for ff in self.freq_factors:
                for det in dets:
                  # set parents of node
                  if pname in self.concat_nodes:
                    penode.add_parent(self.concat_nodes[pname][det][ff])
                  else:
                    if self.engine == 'heterodyne':
                      penode.add_parent(self.fine_heterodyne_nodes[pname][det][ff])
                    if self.engine == 'splinter':
                      if pname in self.splinter_modified_pars:
                        penode.add_parent(self.splinter_nodes_modified[det][ff])
                      elif pname in self.splinter_unmodified_pars:
                        penode.add_parent(self.splinter_nodes_unmodified[det][ff])

            # if using ROQ add first PE node as parent to the rest
            if self.pe_roq:
              if roqinputnode is not None: # add first penode (which generates the ROQ interpolant) as a parent to subsequent nodes
                penode.add_parent(roqinputnode)

              if counter == 0: # get first penode (generating and outputting the ROQ interpolant) to add as parents to subsequent nodes
                roqinputnode = penode
                self.add_node(penode)
                counter = counter+1 # increment "counter", but not "i"
                del nestfiles[-1]   # remove last element of nestfiles
                continue

            # add node to dag
            self.add_node(penode)
            penodes.append(penode)

            # move SNR files into posterior directory
            mvnode = moveNode(mvjob)
            snrsourcefile = os.path.splitext(nestfiles[i])[0]+'_SNR' # source SNR file
            snrdestfile = os.path.join(ffpostdir, 'SNR_%05d.txt' % i) # destination SNR file in posterior directory
            mvnode.set_source(snrsourcefile)
            mvnode.set_destination(snrdestfile)
            mvnode.add_parent(penode)
            self.add_node(mvnode)

            counter = counter+1
            i = i+1

          # add lalapps_nest2pos node to combine outputs/convert to posterior samples
          n2pnode = nest2posNode(n2pjob)
          postfile = os.path.join(ffpostdir, 'posterior_samples_%s.hdf' % pname)
          n2pnode.set_outfile(postfile)     # output posterior file
          n2pnode.set_nest_files(nestfiles) # nested sample files

          n2pnodes[pname].append(n2pnode)

          # add parents
          for pn in penodes:
            n2pnode.add_parent(pn)

          self.add_node(n2pnode) # add node

          # check whether to remove the nested sample files
          if self.pe_clean_nest_samples:
            rmnode = removeNode(rmjob)
            # add name of header file
            rmnode.set_files(nestfiles)
            rmnode.add_parent(n2pnode)
            self.add_node(rmnode)

      if j == 0:
        # add main n2p nodes
        for pname in self.analysed_pulsars:
          self.pe_nest2pos_nodes[pname] = n2pnodes[pname]
      else:
        # add background n2p nodes
        for pname in self.analysed_pulsars:
          self.pe_nest2pos_background_nodes[pname] = n2pnodes[pname]


  def create_prior_file(self, psr, psrdir, detectors, freqfactors, outputpath):
    """
    Create the prior file to use for a particular job defined by a set of detectors, or single detector, and
    a set of frequency factors, or a single frequency factor.

    Return the full output file and the create prior node
    """

    # create the output file
    pname = psr['PSRJ']
    outfile = os.path.join(outputpath, '%s.prior' % pname)

    # if using a pre-made prior file then just create a symbolic link to that file into outputpath
    if self.pe_premade_prior_file != None:
      try:
        os.symlink(self.pe_premade_prior_file, outfile)
      except:
        print("Error... could not create symbolic link to prior file '%s'" % self.pe_premade_prior_file, file=sys.stderr)
        self.error_code = -1
      return outfile

    # check if requiring to add parameters with errors in the .par file to the prior options
    prior_options = {}
    if self.pe_prior_options != None:
      prior_options = deepcopy(self.pe_prior_options)

      if self.pe_use_parameter_errors:
        # create and output a covariance matrix (in the pulsar directory) if it does not already exist
        corfile = os.path.join(psrdir, '%s.cor' % pname)
        fp = open(corfile, 'w')
        fp.write('\t') # indent the list of parameters

        erritems = [] #  list of values with errors

        ignore_pars = ["DM", "START", "FINISH", "NTOA", "TRES", "TZRMJD", "TZRFRQ", "TZRSITE", "NITS", "ELAT", "ELONG"] # keys to ignore from par file

        for paritem in pppu.float_keys:
          if paritem in ignore_pars:
            continue
          if psr['%s_ERR' % paritem] != None and psr['%s_FIT' % paritem] != None: # get values with a given error (suffixed with _ERR)
            if psr['%s_FIT' % paritem] == 1:
              # set Gaussian prior with mean being the parameter value and sigma being the error
              if paritem in ['RA_RAD', 'DEC_RAD']:
                itemname = paritem.replace('_RAD', '')
              else:
                itemname = paritem
              prior_options[itemname] = {'priortype': 'gaussian', 'ranges': [psr[paritem], psr['%s_ERR' % paritem]]}

              fp.write(itemname+' ')
              erritems.append(itemname)

        if len(erritems) > 0:
          fp.write('\n')

          for i, ei in enumerate(erritems): # have all values uncorrelated except w0 and T0 or wdot and Pb, which should be highly correlated for small eccentricity binaries
            fp.write(ei+'\t')
            for j in range(i+1):
              if i == j:
                fp.write('1 ') # diagonal values of correlation coefficient matrix
              else:
                # check if an eccentricity of between 0 and 0.001
                ecc = 0.0
                if psr['E'] != None:
                  ecc = psr['E']
                elif psr['ECC'] != None:
                  ecc = psr['ECC']

                if ecc >= 0. and ecc < 0.001:
                  if ((ei == 'T0' and erritems[j] == 'OM') or (ei == 'OM' and erritems[j] == 'T0')) and ('T0' in erritems and 'OM' in erritems):
                    fp.write('0.9999 ') # set parameters to be highly correlated (although not fully due to issues with fully correlated parameters)
                  elif ((ei == 'PB' and erritems[j] == 'OMDOT') or (ei == 'OMDOT' and erritems[j] == 'PB')) and ('PB' in erritems and 'OMDOT' in erritems):
                    fp.write('0.9999 ') # set parameters to be highly correlated (although not fully due to issues with fully correlated parameters)
                  else:
                    fp.write('0 ')
                else:
                  fp.write('0 ') # set everything else to be uncorrelated
            fp.write('\n')
          fp.close()

        if len(erritems) > 0:
          self.pe_cor_files[pname] = corfile
        else: # no error value were found so remove corfile
          os.remove(corfile)

    # check if deriving amplitude priors
    if self.pe_derive_amplitude_prior:
      # open output prior file
      try:
        fp = open(outfile, 'w')
      except:
        print("Error... could no open prior file '%s'" % outfile, file=sys.stderr)
        self.error_code = -1
        return outfile

      # write out any priors that have been given
      for prioritem in prior_options:
        if 'priortype' not in prior_options[prioritem]:
          print("Error... no 'priortype' given for parameter '%s'" % prioritem, file=sys.stderr)
          self.error_code = -1
          return outfile
        if 'ranges' not in prior_options[prioritem]:
          print("Error... no 'ranges' given for parameter '%s'" % prioritem, file=sys.stderr)
          self.error_code = -1
          return outfile

        ptype = prior_options[prioritem]['priortype']
        rangevals = prior_options[prioritem]['ranges']

        if len(rangevals) != 2:
          print("Error... 'ranges' for parameter '%s' must be a list or tuple with two entries" % prioritem, file=sys.stderr)
          self.error_code = -1
          return outfile

        fp.write('%s\t%s\t%.16le\t%.16le\n' % (prioritem, ptype, rangevals[0], rangevals[1]))

      # set the required amplitude priors
      requls = {} # dictionary to contain the required upper limits
      if self.pe_model_type == 'waveform':
        if 2. in self.freq_factors:
          requls['C22'] = None
        if 1. in self.freq_factors:
          requls['C21'] = None
      elif self.pe_model_type == 'source':
        if len(self.freq_factors) == 1:
          requls['H0'] = None
        if len(self.freq_factors) == 2:
          if 1. in self.freq_factors and 2. in self.freq_factors:
            requls['I21'] = None
            requls['I31'] = None

      if len(requls) == 0:
        print("Error... unknown frequency factors or model type in configuration file.", file=sys.stderr)
        self.error_code = -1
        return outfile

      # try and get the file containing previous upper limits
      if os.path.isfile(self.pe_amplitude_prior_file):
        # check file can be read
        if self.pe_prior_info is None:
          try:
            fpp = open(self.pe_amplitude_prior_file, 'r')
            self.pe_prior_info = json.load(fpp) # should be JSON file
            fpp.close()
          except:
            print("Error... could not parse prior file '%s'." % self.pe_amplitude_prior_file, file=sys.stderr)
            self.error_code = -1
            return outfile

        # see if pulsar is in prior file
        if pname in self.pe_prior_info:
          uls = self.pe_prior_info[pname]
          for ult in requls:
            if ult == 'C22':
              if 'C22UL' not in uls and 'H0UL' in uls:
                # use 'H0' value for 'C22' if present
                requls['C22'] = uls['H0UL']
            else:
              if ult+'UL' in uls:
                requls[ult] = uls[ult+'UL']

      # if there are some required amplitude limits that have not been obtained try and get amplitude spectral densities
      freq = psr['F0']

      if None in requls.values() and freq > 0.0:
        if self.pe_amplitude_prior_asds != None and self.pe_amplitude_prior_obstimes != None:
          asdfiles = self.pe_amplitude_prior_asds
          obstimes = self.pe_amplitude_prior_obstimes

          if not isinstance(asdfiles, dict): # if a single file is given convert into dictionary
            asdfilestmp = {}
            obstimestmp = {}
            asdfilestmp['det'] = asdfiles
            obstimestmp['det'] = float(obstimes)
            asdfiles = asdfilestmp
            obstimes = obstimestmp

          asdlist = []
          for dk in asdfiles: # read in all the ASD files
            if dk not in obstimes:
              print("Error... no corresponding observation times for detector '%s'" % dk, file=sys.stderr)
              self.error_code = -1
              return outfile
            else:
              if not isinstance(obstimes[dk], float) and not isinstance(obstimes[dk], int):
                print("Error... observation time must be a float or int.", file=sys.stderr)
                self.error_code = -1
                return outfile
              if dk not in self.pe_prior_asds:
                if not os.path.isfile(asdfiles[dk]):
                  print("Error... ASD file '%s' does not exist." % asdfiles[dk], file=sys.stderr)
                  self.error_code = -1
                  return outfile
                else:
                  try:
                    self.pe_prior_asds[dk] = np.loadtxt(asdfiles[dk], comments=['%', '#'])
                  except:
                    print("Error... could not load file '%s'." % asdfiles[dk], file=sys.stderr)
                    self.error_code = -1
                    return outfile

              asd = self.pe_prior_asds[dk]
              asdv = [] # empty array
              if 1. in self.freq_factors and (asd[0,0] <= freq and asd[-1,0] >= freq): # add ASD at 1f
                idxf = (np.abs(asd[:,0]-freq)).argmin() # get value nearest required frequency
                asdv.append(asd[idxf,1])
              if 2. in self.freq_factors and (asd[0,0] <= 2.*freq and asd[-1,0] >= 2.*freq):
                idxf = (np.abs(asd[:,0]-2.*freq)).argmin() # get value nearest required frequency
                asdv.append(asd[idxf,1])

              if len(asdv) > 0:
                asdlist.append(np.array(asdv)**2/(obstimes[dk]*86400.))
              else:
                print("Error... frequency range in ASD file does not span pulsar frequency.", file=sys.stderr)
                self.error_code = -1
                return outfile


          # get upper limit spectrum (harmonic mean of all the weighted spectra)
          mspec = np.zeros(len(self.freq_factors))
          for asdv in asdlist:
            # interpolate frequencies
            mspec = mspec + (1./asdv)

          mspec = np.sqrt(1./mspec) # final weighted spectrum
          ulspec = 10.8*mspec # scaled to given "averaged" 95% upper limit estimate

          # set upper limits for creating priors
          if self.pe_model_type == 'waveform':
            if 1. in self.freq_factors:
              if requls['C21'] == None:
                requls['C21'] = ulspec[self.freq_factors.index(1.0)]
            if 2. in self.freq_factors:
              if requls['C22'] == None:
                requls['C22'] = ulspec[self.freq_factors.index(2.0)]
          if self.pe_model_type == 'source':
            if len(self.freq_factors) == 1:
              if requls['H0'] == None:
                requls['H0'] = ulspec[0]
            else:
              if 1. in self.freq_factors and 2. in self.freq_factors:
                # set both I21 and I31 to use the maximum of the 1f and 2f es
                if requls['I21'] == None:
                  requls['I21'] = np.max(ulspec)
                if requls['I31'] == None:
                  requls['I31'] = np.max(ulspec)

      # get amplitude prior type
      if self.pe_amplitude_prior_type not in ['fermidirac', 'uniform']:
        print("Error... prior type must be 'fermidirac' or 'uniform'", file=sys.stderr)
        self.error_code = -1
        return outfile

      # go through required upper limits and output a Fermi-Dirac prior that also has a 95% limit at that value
      for ult in requls:
        if requls[ult] == None:
          print("Error... a required upper limit for '%s' is not available." % ult, file=sys.stderr)
          self.error_code = -1
          return outfile
        else:
          if self.pe_amplitude_prior_type == 'fermidirac':
            try:
              b, a = self.fermidirac_rsigma(requls[ult])
            except:
              print("Error... problem deriving the Fermi-Dirac prior for '%s'." % ult, file=sys.stderr)
              self.error_code = -1
              return outfile
          else:
            a = 0. # uniform prior bound at 0
            b = requls[utl]/0.95 # stretch limit to ~100% bound

          fp.write('%s\t%s\t%.16le\t%.16le\n' % (ult, self.pe_amplitude_prior_type, a, b))

      fp.close()
    else:
      # make prior file from parameters
      try:
        fp = open(outfile, 'w')
      except:
        print("Error... could not write prior file '%s'" % outfile, file=sys.stderr)
        self.error_code = -1
        return outfile

      for prioritem in prior_options:
        ptype = prior_options[prioritem]['priortype']
        rangevals = prior_options[prioritem]['ranges']
        if len(rangevals) != 2:
          print("Error... the ranges in the prior for '%s' are not set properly" % prioritem, file=sys.stderr)
          self.error_code = -1
          return outfile
        fp.write("%s\t%s\t%.9e\t%.9e\n" % (prioritem, ptype, rangevals[0], rangevals[1]))
      fp.close()

    return outfile


  def fermidirac_rsigma(self, ul, mufrac=0.4, cdf=0.95):
    """
    Calculate the r and sigma parameter of the Fermi-Dirac distribution to be used.

    Based on the definition of the distribution given in https://www.authorea.com/users/50521/articles/65214/_show_article
    the distribution will be defined by a mu parameter at which the distribution has 50% of it's maximum
    probability, and mufrac which is the fraction of mu defining the range from which the distribution falls from
    97.5% of the maximum down to 2.5%. Using an upper limit defining a given cdf of the distribution the parameters
    r and sigma will be returned.
    """

    Z = 7.33 # factor that defined the 97.5% -> 2.5% probability attenuation band around mu
    r = 0.5*Z/mufrac # set r

    # using the Fermi-Dirac CDF to find sigma given a distribution where the cdf value is found at ul
    solution = optimize.root(lambda s: cdf*np.log(1.+np.exp(r))-np.log(1.+np.exp(-r))-(ul/s)-np.log(1.+np.exp((ul/s)-r)), ul)
    sigma = solution.x[0]

    return r, sigma


  def setup_heterodyne(self):
    """
    Setup the coarse and fine heterodyne jobs/nodes.
    """

    # get executable
    self.heterodyne_exec = self.get_config_option('heterodyne', 'heterodyne_exec', default='lalapps_heterodyne_pulsar')
    if self.error_code != 0: return

    # check file exists and is executable
    if not os.path.isfile(self.heterodyne_exec) or not os.access(self.heterodyne_exec, os.X_OK):
      print("Warning... 'heterodyne_exec' in '[heterodyne]' does not exist or is not an executable. Try finding code in path.")
      hetexec = self.find_exec_file('lalapps_heterodyne_pulsar')

      if hetexec == None:
        print("Error... could not find 'lalapps_heterodyne_pulsar' in 'PATH'", file=sys.stderr)
        self.error_code = -1
        return
      else:
        self.heterodyne_exec = hetexec

    # Get Condor universe (default to vanilla)
    self.heterodyne_universe = self.get_config_option('heterodyne', 'universe', default='vanilla')
    if self.error_code != 0: return

    # Get some general setup data
    self.coarse_heterodyne_filter_knee = self.get_config_option('heterodyne', 'filter_knee', 'float', default=0.25)
    self.coarse_heterodyne_sample_rate = self.get_config_option('heterodyne', 'coarse_sample_rate', 'int', default=16384)
    self.coarse_heterodyne_resample_rate = self.get_config_option('heterodyne', 'coarse_resample_rate', 'float', default=1.0)
    self.coarse_heterodyne_channels = self.get_config_option('heterodyne', 'channels', 'dict')
    self.coarse_heterodyne_binary_output = self.get_config_option('heterodyne', 'binary_output', 'boolean', default=True)
    self.coarse_heterodyne_gzip_output = self.get_config_option('heterodyne', 'gzip_coarse_output', 'boolean', default=False)
    if self.error_code != 0: return
    if self.coarse_heterodyne_binary_output and self.coarse_heterodyne_gzip_output:
      print("Warning... cannot output coarse heterdyned data as gzip and binary. Defaulting to binary output.")
      self.coarse_heterodyne_gzip_output = False

    self.fine_heterodyne_resample_rate = self.get_config_option('heterodyne', 'fine_resample_rate', 'string', default='1/60')
    self.fine_heterodyne_stddev_thresh = self.get_config_option('heterodyne', 'stddev_thresh', 'float', default=3.5)
    self.fine_heterodyne_gzip_output = self.get_config_option('heterodyne', 'gzip_fine_output', 'boolean', default=True)
    if self.error_code != 0: return

    # create heterodyne job
    requestmemory = None
    if self.coarse_heterodyne_gzip_output:
      # if gzipping output then memory requirements may be an issue so request 2000Mb of memory
      requestmemory = 2000
    chetjob = heterodyneJob(self.heterodyne_exec, univ=self.heterodyne_universe, accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir, subprefix='coarse', requestmemory=requestmemory)
    fhetjob = heterodyneJob(self.heterodyne_exec, univ=self.heterodyne_universe, accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir, subprefix='fine')

    self.processed_files = {} # dictionary of processed (fine heterodyned files)
    self.fine_heterodyne_nodes = {} # dictionary for fine heterodyne nodes to use as parents to later jobs

    self.modified_pulsars_segment_list_tmp = {}
    getmodsciencesegs = {} # flag for modified pulsars setting whether script needs to get the science segment list
    segfiletimes = {} # (for unmodified pulsars) store segment files that have already been generated (keyed by the start time) to save repeated segment list finding calls
    for ifo in self.ifos:
      getmodsciencesegs[ifo] = True
      segfiletimes[ifo] = {}

    # loop through all pulsars
    for pname in self.analysed_pulsars:
      par = self.analysed_pulsars[pname]
      modified_pulsar = unmodified_pulsar = False

      # check if pulsar is new/has modified par file, or has an unmodified par file
      if par in self.modified_pulsars:
        modified_pulsar = True
      elif par in self.unmodified_pulsars:
        unmodified_pulsar = True

      # get ephemeris
      earthfile, sunfile, timefile = self.get_ephemeris(pppu.psr_par(par))
      if self.error_code != 0: return

      segfiles = {}

      self.fine_heterodyne_nodes[pname] = {}
      self.processed_files[pname] = {}

      # loop through detectors and set up directory structure and get science segments on first pass
      for ifo in self.ifos:
        psrdir = os.path.join(self.preprocessing_base_dir[ifo], pname)
        self.mkdirs(psrdir)
        if self.error_code != 0: return

        datadir = os.path.join(psrdir, 'data')
        self.mkdirs(datadir)
        if self.error_code != 0: return

        coarsedir = os.path.join(datadir, 'coarse')
        self.mkdirs(coarsedir)
        if self.error_code != 0: return

        finedir = os.path.join(datadir, 'fine')
        self.mkdirs(finedir)
        if self.error_code != 0: return

        segfiles[ifo] = os.path.join(psrdir, 'segments.txt')

        # get segment list
        if modified_pulsar:
          if getmodsciencesegs[ifo]:
            self.modified_pulsars_segment_list_tmp[ifo] = os.path.join(self.preprocessing_base_dir[ifo], 'segments_tmp.txt')
            self.find_data_segments(self.initial_start[ifo], self.endtime[ifo], ifo, self.modified_pulsars_segment_list_tmp[ifo])

          # copy segment list into pulsar directories
          try:
            shutil.copy2(self.modified_pulsars_segment_list_tmp[ifo], segfiles[ifo])
          except:
            print("Error... could not copy segment list into pulsar directory", file=sys.stderr)
            self.error_code = -1
            return

          if getmodsciencesegs[ifo]: getmodsciencesegs[ifo] = False

          # remove any "previous_segments.txt" file if it exists
          prevsegs = os.path.join(os.path.dirname(segfiles[ifo]), 'previous_segments.txt')
          if os.path.isfile(prevsegs):
            try:
              os.remove(prevsegs)
            except:
              print("Warning... previous segment list file '%s' could not be removed" % prevsegs)
        elif unmodified_pulsar:
          # append current segment file (if it exists) to file containing previous segments
          if os.path.isfile(segfiles[ifo]):
            # get filename for list containing all previous segments
            prevsegs = os.path.join(os.path.dirname(segfiles[ifo]), 'previous_segments.txt')
            self.segment_file_update.append((segfiles[ifo], prevsegs)) # add to list of files to be concatenated together at the end (i.e. provided no errors have occurred)

          if self.autonomous:
            # if running in automatic mode make sure we don't miss data by using the end time in the previous segment
            # file as the new start time (rather than self.starttime)
            if os.path.isfile(segfiles[ifo]):
              # get end time from segment file
              p = sp.check_output("tail -1 " + segfiles[ifo], shell=True)
              if len(p) != 0:
                self.starttime[ifo] = int(p.split()[1])
              else:
                print("Error... could not get end time out of previous segment file '%s'" % segfile, file=sys.stderr)
                self.error_code = -1
                return

          # check if a segment file for the given start time has already been created, and if so use that
          if self.starttime[ifo] in segfiletimes[ifo]:
            shutil.copy2(segfiletimes[ifo][self.starttime[ifo]], segfiles[ifo])
          else:
            segfiletimes[ifo][self.starttime[ifo]] = segfiles[ifo]

            # create new segment file
            self.find_data_segments(self.starttime[ifo], self.endtime[ifo], ifo, segfiles[ifo])

        self.fine_heterodyne_nodes[pname][ifo] = {}
        self.processed_files[pname][ifo] = {}

        # loop through frequency factors for analysis
        for freqfactor in self.freq_factors:
          if not freqfactor%1.: # for integers just output directory as e.g. 2f
            freqfacdircoarse = os.path.join(coarsedir, '%df' % int(freqfactor))
            freqfacdirfine = os.path.join(finedir, '%df' % int(freqfactor))
          else: # for non-integers use 2 d.p. for dir name
            freqfacdircoarse = os.path.join(coarsedir, '%.2ff' % freqfactor)
            freqfacdirfine = os.path.join(finedir, '%.2ff' % freqfactor)

          self.mkdirs(freqfacdircoarse)
          if self.error_code != 0: return
          self.mkdirs(freqfacdirfine)
          if self.error_code != 0: return

          # create output files
          if self.coarse_heterodyne_binary_output:
            coarseoutput = os.path.join(freqfacdircoarse, 'coarse-%s-%d-%d.bin' % (ifo, int(self.initial_start[ifo]), int(self.endtime[ifo])))
          else:
            coarseoutput = os.path.join(freqfacdircoarse, 'coarse-%s-%d-%d.txt' % (ifo, int(self.initial_start[ifo]), int(self.endtime[ifo])))

          # create coarse heterodyne node
          coarsenode = heterodyneNode(chetjob)

          # add data find parent to coarse job
          coarsenode.add_parent(self.datafind_nodes[ifo])

          # set data, segment location, channel and output location
          coarsenode.set_data_file(self.cache_files[ifo])
          coarsenode.set_seg_list(segfiles[ifo])
          coarsenode.set_channel(self.coarse_heterodyne_channels[ifo])
          coarsenode.set_output_file(coarseoutput)
          if self.coarse_heterodyne_binary_output:
            coarsenode.set_binoutput()
          if self.coarse_heterodyne_gzip_output:
            coarsenode.set_gzip_output()

          # set some coarse heterodyne info
          coarsenode.set_ifo(ifo)         # detector
          coarsenode.set_het_flag(0)      # perform coarse heterodyne
          coarsenode.set_pulsar(pname)    # pulsar name
          coarsenode.set_param_file(par)  # pulsar parameter file
          coarsenode.set_filter_knee(self.coarse_heterodyne_filter_knee)
          coarsenode.set_sample_rate(self.coarse_heterodyne_sample_rate)
          coarsenode.set_resample_rate(self.coarse_heterodyne_resample_rate)
          coarsenode.set_freq_factor(freqfactor) # multiplicative factor for the rotation frequency

          self.add_node(coarsenode)

          # create fine heterodyne node
          finenode = heterodyneNode(fhetjob)

          # add coarse parent to fine job
          finenode.add_parent(coarsenode)

          # create output files
          fineoutput = os.path.join(freqfacdirfine, 'fine-%s-%d-%d.txt' % (ifo, int(self.initial_start[ifo]), int(self.endtime[ifo])))

          # set data, segment location and output location
          if self.coarse_heterodyne_gzip_output:
            finenode.set_data_file(coarseoutput+'.gz')
          else:
            finenode.set_data_file(coarseoutput)

          if self.coarse_heterodyne_binary_output:
            finenode.set_bininput()

          finenode.set_seg_list(segfiles[ifo])
          finenode.set_output_file(fineoutput)

          # set fine heterodyne info
          finenode.set_ifo(ifo)
          finenode.set_het_flag(1)      # perform fine heterodyne
          finenode.set_pulsar(pname)    # pulsar name
          finenode.set_param_file(par)  # pulsar parameter file
          finenode.set_sample_rate(self.coarse_heterodyne_resample_rate) # use resample rate from coarse heterodyne
          finenode.set_resample_rate(self.fine_heterodyne_resample_rate)
          finenode.set_filter_knee(self.coarse_heterodyne_filter_knee)
          finenode.set_freq_factor(freqfactor)
          finenode.set_stddev_thresh(self.fine_heterodyne_stddev_thresh)
          finenode.set_ephem_earth_file(earthfile)
          finenode.set_ephem_sun_file(sunfile)
          finenode.set_ephem_time_file(timefile)

          if self.fine_heterodyne_gzip_output:
            finenode.set_gzip_output()

          self.add_node(finenode)

          # record fine nodes and files
          self.fine_heterodyne_nodes[pname][ifo][freqfactor] = finenode
          if self.fine_heterodyne_gzip_output:
            fineoutput = fineoutput + '.gz' # append .gz to recorded file name

          if modified_pulsar:
            self.processed_files[pname][ifo][freqfactor] = [fineoutput]
          elif unmodified_pulsar:
            # check for other fine heterodyned files already in the directory
            hetfilescheck = [os.path.join(freqfacdirfine, hf) for hf in os.listdir(freqfacdirfine) if 'fine' in hf]
            hetfilescheck.sort()

            # if gzipping the current file, but older files are not gzipped, gzip them now
            if self.fine_heterodyne_gzip_output:
              for i, hf in enumerate(hetfilescheck):
                if '.gz' not in hf:
                  # try gzipping file
                  p = sp.Popen("gzip " + hf, shell=True)
                  out, err = p.communicate()
                  if p.returncode != 0:
                    print("Error... could not gzip previous fine heterdyned file '%s': %s, %s" % (hf, out, err), file=sys.stderr)
                    self.error_code = -1
                    return

                  hetfilescheck[i] = hf + '.gz' # add .gz suffix
            else: # alternatively, if not gzipping current file, but older files are gzipped then gunzip them now
              for i, hf in enumerate(hetfilescheck):
                if '.gz' in hf:
                  # try gunzipping file
                  p = sp.Popen("gunzip " + hf, shell=True)
                  out, err = p.communicate()
                  if p.returncode != 0:
                    print("Error... could not gunzip previous fine heterdyned file '%s': %s, %s" % (hf, out, err), file=sys.stderr)
                    self.error_code = -1
                    return

            self.processed_files[pname][ifo][freqfactor] = hetfilescheck
            self.processed_files[pname][ifo][freqfactor].append(fineoutput) # append new file

    # remove temporary segment file
    if len(self.modified_pulsars) > 0:
      for ifo in self.ifos:
        try:
          if os.path.isfile(self.modified_pulsars_segment_list_tmp[ifo]):
            os.remove(self.modified_pulsars_segment_list_tmp[ifo])
        except:
          print("Warning... could not remove temporary segment list '%s'" % self.modified_pulsars_segment_list_tmp[ifo])


  def setup_splinter(self):
    """
    Setup the Spectral Interpolation jobs/nodes.
    """

    # NOTE: splinter runs on multiple pulsars at once, so requires a directory containing the necessary pulsars,
    # therefore for new/modified par files need to be linked to from one directory, and unmodifed par files need
    # to be linked to from another directory

    # Spectral interpolation output files have the format Splinter_PSRJNAME_DET e.g. Splinter_J0534+2200_H1

    # get executable
    self.splinter_exec = self.get_config_option('splinter', 'splinter_exec', default='lalapps_SplInter')
    if self.error_code != 0: return

    self.splinter_modified_pars = {}
    self.splinter_unmodified_pars = {}

    # check file exists and is executable
    if not os.path.isfile(self.splinter_exec) or not os.access(self.splinter_exec, os.X_OK):
      print("Warning... 'splinter_exec' in '[splinter]' does not exist or is not an executable. Try finding code in path.")

      splexec = self.find_exec_file('lalapps_SplInter')

      if splexec == None:
        print("Error... could not find 'lalapps_SplInter' in 'PATH'", file=sys.stderr)
        self.error_code = -1
        return
      else:
        self.splinter_exec = splexec

    # Get Condor universe (default to vanilla)
    self.splinter_universe = self.get_config_option('splinter', 'universe', default='vanilla')
    if self.error_code != 0: return

    # create splinter job
    spljob = splinterJob(self.splinter_exec, univ=self.splinter_universe, accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir)

    # get splinter options
    self.splinter_bandwidth = self.get_config_option('splinter', 'bandwidth', 'float', 0.3)
    self.splinter_freq_range = self.get_config_option('splinter', 'freq_range', 'list', [30., 2000.])
    self.splinter_stddev_thresh = self.get_config_option('splinter', 'stddev_thresh', 'float', 3.5)
    self.splinter_min_seg_length = self.get_config_option('splinter', 'min_seg_length', 'int', 1800)
    self.splinter_gzip_output = self.get_config_option('splinter', 'gzip_output', 'boolean', False)
    if self.error_code != 0: return

    # create splinter nodes (one for unmodified pulsars and one for modified pulsars)
    self.splinter_nodes_modified = {}
    self.splinter_nodes_unmodified = {}

    # set location for SplInter data to eventually be copied to
    self.splinter_data_location = {}

    # check for whether there are any modified or unmodified pulsars
    modpars = False
    unmodpars = False
    if len(self.modified_pulsars) > 0: modpars = True
    if len(self.unmodified_pulsars) > 0: unmodpars = True

    for ifo in self.ifos:
      # Create splinter base directory to contain data products and par file directories
      self.splinter_dir = os.path.join(self.preprocessing_base_dir[ifo], 'splinter')
      self.mkdirs(self.splinter_dir)
      if self.error_code != 0: return

      # Create par file directories: one containing links to files for modified pulsars and one for unmodified pulsars - if directories already exist then remove files from them
      for modsuffix in ['modified', 'unmodified']:
        pardir = os.path.join(self.splinter_dir, modsuffix)

        if modsuffix == 'modified':
          if modpars > 0:
            self.splinter_modified_pulsar_dir = pardir
            parlist = self.modified_pulsars
            self.splinter_nodes_modified[ifo] = {}
          else: continue

        if modsuffix == 'unmodified':
          if unmodpars > 0:
            self.splinter_unmodified_pulsar_dir = pardir
            parlist = self.unmodified_pulsars
            self.splinter_nodes_unmodified[ifo] = {}
          else: continue

        if os.path.isdir(pardir):
          # remove all files within the directory
          for f in os.listdir(pardir):
            try:
              os.remove(os.path.join(pardir, f))
            except:
              print("Warning... problem removing par file '%s' from '%s'. This file may be overwritten." % (f, pardir))
        else: # make the directory and make symbolic links to all the modified par files in to
          self.mkdirs(pardir)
          if self.error_code != 0: return

        for par in parlist:
          try:
            psr = pppu.psr_par(par)
            pname = psr['PSRJ']

            parlink = os.path.join(pardir, os.path.basename(par))
            if modsuffix == 'modified': self.splinter_modified_pars[pname] = parlink
            if modsuffix == 'unmodified': self.splinter_unmodified_pars[pname] = parlink
            os.symlink(par, parlink)

            # create dictionary to hold list of names of the output files that will be created by lalapps_SplInter
            if pname not in self.processed_files:
              self.processed_files[pname] = {}
              self.splinter_data_location[pname] = {}

            self.processed_files[pname][ifo] = {}
            self.splinter_data_location[pname][ifo] = {}

            # create directory for the output file to eventually moved into
            psrdir = os.path.join(preprocessing_base_dir[ifo], pname)
            self.mkdirs(psrdir)
            if self.error_code != 0: return

            datadir = os.path.join(psrdir, 'data')
            self.mkdirs(datadir)
            if self.error_code != 0: return

            splintercpydir = os.path.join(datadir, 'splinter')
            self.mkdirs(splintercpydir)
            if self.error_code != 0: return

            for freqfactor in self.freq_factors:
              if not freqfactor%1.: # for integers just output director as e.g. 2f
                ffdir = os.path.join(splintercpydir, '%df' % int(freqfactor))
                splinterdir = os.path.join(self.splinter_dir, '%df' % int(freqfactor))
              else: # for non-integers use 2 d.p. for dir name
                ffdir = os.path.join(splintercpydir, '%.3ff' % int(freqfactor))
                splinterdir = os.path.join(self.splinter_dir, '%.2ff' % freqfactor)

              # the name of the file that will be output by lalapps_Splinter
              self.processed_files[pname][ifo][freqfactor] = [os.path.join(splinterdir, 'Splinter_%s_%s' % (pname, ifo))]

              # the location to move that file to
              self.mkdirs(ffdir)
              if self.error_code != 0: return
              self.splinter_data_location[pname][ifo][freqfactor] = ffdir
          except:
            print("Warning... could not create link to par file '%s' in '%s'. This file may be overwritten." % (par, pardir))

      # reset modpars and unmodpars based on whether any files are in self.splinter_(un)modified_pars
      if len(self.splinter_modified_pars) == 0: modpars = False
      if len(self.splinter_unmodified_pars) == 0: unmodpars = False

      # Create segment list for modified pulsars
      modsegfile = None
      if modpars:
        modsegfile = os.path.join(self.preprocessing_base_dir[ifo], 'segments_modified.txt')
        self.find_data_segments(self.initial_start[ifo], self.endtime[ifo], ifo, modsegfile)

      # Create segment list for unmodified pulsars
      unmodsegfile = None
      if unmodpars:
        unmodsegfile = os.path.join(self.preprocessing_base_dir[ifo], 'segments_unmodified.txt')

        if self.autonomous:
          # if running in automatic mode make sure we don't miss data by using the end time in the previous segment
          # file as the new start time (rather than self.starttime)
          if os.path.isfile(unmodsegfile):
            # get end time from segment list
            p = sp.check_output("tail -1 " + unmodsegfile, shell=True)
            if len(p) != 0:
              self.starttime[ifo] = int(p.split()[1])
            else:
              print("Error... could not get end time out of previous segment file '%s'" % unmodsegfile, file=sys.stderr)
              self.error_code = -1
              return

        # create new segment file
        self.find_data_segments(self.starttime[ifo], self.endtime[ifo], ifo, unmodsegfile)

        # append segments to file containing all previously analysed segments
        # get filename for list containing all previous segments
        prevsegs = os.path.join(self.preprocessing_base_dir[ifo], 'previous_segments.txt')
        self.segment_file_update.append((unmodsegfile, prevsegs)) # add to list of files to be concatenated together at the end (i.e. provided no errors have occurred)

      # loop through frequency factors for analysis
      for freqfactor in self.freq_factors:
        if not freqfactor%1.: # for integers just output director as e.g. 2f
          splinterdir = os.path.join(self.splinter_dir, '%df' % int(freqfactor))
        else: # for non-integers use 2 d.p. for dir name
          splinterdir = os.path.join(self.splinter_dir, '%.2ff' % freqfactor)

        self.mkdirs(splinterdir)
        if self.error_code != 0: return

        # create nodes (first for modified pulsars and second for unmodified)
        splsegfiles = [modsegfile, unmodsegfile]
        splpardirs = [self.splinter_modified_pulsar_dir, self.splinter_unmodified_pulsar_dir]

        for idx, splbool in enumerate([modpars, unmodpars]):
          if splbool:
            splnode = splinterNode(spljob)

            splnode.add_parent(self.datafind_nodes[ifo])

            splnode.set_output_dir(splinterdir)     # output directory
            splnode.set_param_dir(splpardirs[idx])  # pulsar parameter file directory
            splnode.set_seg_list(splsegfiles[idx])  # science segment list file
            splnode.set_freq_factor(freqfactor)     # frequency scaling factor
            splnode.set_ifo(ifo)                    # detector

            splnode.set_bandwidth(self.splinter_bandwidth)            # bandwidth of data to use
            splnode.set_min_seg_length(self.splinter_min_seg_length)  # minimum length of usable science segments
            splnode.set_start_freq(self.splinter_freq_range[0])       # low frequency cut-off to read from SFTs
            splnode.set_end_freq(self.splinter_freq_range[1])         # high frequency cut-off to read from SFTs
            splnode.set_stddev_thresh(self.splinter_stddev_thresh)    # threshold for vetoing data
            splnode.set_ephem_dir(self.ephem_path)                    # path to solar system ephemeris files

            if idx == 0: self.splinter_nodes_modified[ifo][freqfactor] = splnode
            else: self.splinter_nodes_unmodified[ifo][freqfactor] = splnode
            self.add_node(splnode) # add node to DAG


  def get_ephemeris(self, psr):
    """
    Get the ephemeris file information based on the content of the psr file
    """

    # get ephemeris value from par file
    ephem = psr['EPHEM']
    if ephem is None: # if not present default to DE405
      ephem = 'DE405'

    # get the time units (TDB)
    units = psr['UNITS']
    if units is None: # default to TEMPO2 standard of TCB
      units = 'TCB'

    earthfile = os.path.join(self.ephem_path, 'earth00-19-%s.dat.gz' % ephem)
    sunfile = os.path.join(self.ephem_path, 'sun00-19-%s.dat.gz' % ephem)

    if units == 'TDB':
      timefile = os.path.join(self.ephem_path, 'tdb_2000-2019.dat.gz')
    else:
      timefile = os.path.join(self.ephem_path, 'te405_2000-2019.dat.gz')

    if not os.path.isfile(earthfile):
      print("Error... Earth ephemeris file '%s' does not exist" % earthfile, file=sys.stderr)
      self.error_code = -1
      return

    if not os.path.isfile(sunfile):
      print("Error... Sun ephemeris file '%s' does not exist" % sunfile, file=sys.stderr)
      self.error_code = -1
      return

    if not os.path.isfile(timefile):
      print("Error... time ephemeris file '%s' does not exist" % timefile, file=sys.stderr)
      self.error_code = -1
      return

    return earthfile, sunfile, timefile


  def concatenate_files(self):
    """
    Create jobs to concatenate fine heterodyned/Splinter data files in cases where multiple files exist (e.g. in automated search).
    Go though the processed file list and find ones that have more than one file, also also remove previous files.
    """

    rmjob = removeJob(accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir, rundir=self.run_dir) # job for removing old files
    self.remove_job = rmjob

    self.concat_nodes = {} # concatenation job nodes

    # loop over pulsars
    for pitem in self.processed_files: # pitems will be pulsar names
      pifos = self.processed_files[pitem]

      # loop through detectors
      for pifo in pifos:
        ffs = pifos[pifo]

        # loop through frequency factors
        for ff in ffs:
          finefiles = ffs[ff]
          concatnode = None
          subloc = None
          prevfile = None
          newfinefile = None

          # check for more than one file
          if self.engine == 'heterodyne': # do this for heterodyned data
            if len(finefiles) > 1:
              if pitem not in self.concat_nodes:
                self.concat_nodes[pitem] = {}

              if pifo not in self.concat_nodes[pitem]:
                self.concat_nodes[pitem][pifo] = {}

              # get start time of first file and end time of last file (assuming files have name fine-det-start-end.txt)
              firststart = os.path.basename(finefiles[0]).split('-')[2]
              lastend = os.path.basename(finefiles[-1]).split('-')[3]
              lastend = lastend.replace('.txt', '')
              lastend = lastend.replace('.gz', '')

              # create new file name for concatenated file
              newfinefile = os.path.join(os.path.dirname(finefiles[0]), 'fine-%s-%s-%s.txt' % (pifo, firststart, lastend))
              if self.fine_heterodyne_gzip_output:
                newfinefile = newfinefile + '.gz'

              catfiles = finefiles
              parent = self.fine_heterodyne_nodes[pitem][pifo][ff] # add equivalent fine heterodyned node as parent

              # create new concat job for each case (each one uses it's own sub file)
              subloc = os.path.join(os.path.dirname(finefiles[0]), 'concat.sub')
          elif self.engine == 'splinter': # do this for splinter data
            # check if final location already contains a file
            prevfile = os.listdir(self.splinter_data_location[pitem][pifo][ff])

            if len(prevfile) > 1:
              print("Error... more than one previous Splinter file in directory '%s'" % self.splinter_data_location[pitem][pifo][ff])
              self.error_code = -1
              return

            if pitem in self.splinter_modified_pars: # for modified pulsars set start time (for file name) from run values
              startname = str(self.starttime[ifo])
              catfiles = [finefiles] # just cat (in this case essentially just copying) the single file
              parent = self.splinter_nodes_modified[pifo][ff]
            else: # a previous file exists use the start time from that (for file name)
              if len(prevfile) == 1:
                try:
                  startname = os.path.basename(prevfile).split('-')[1]
                except:
                  print("Warning... could not get previous start time from Splinter file name '%s'. Using start time from this run: '%d'" % (prevfile, self.starttime[ifo]))
                  startname = str(self.starttime[ifo])

                catfiles = [os.path.join(self.splinter_data_location[pitem][pifo][ff], prevfile[0]), finefiles]
              else:
                startname = str(self.starttime[ifo])
              parent = self.splinter_nodes_unmodified[pifo][ff]

            endname = str(self.endtime[ifo])

            # create new file name containing analysis time stamps
            newfinefile = os.path.join(self.splinter_data_location[pitem][pifo][ff], '%s-%s-%s.txt' % ((os.path.basename(finefiles)).strip('.gz'), startname, self.endname))
            if self.splinter_gzip_output:
              newfinefile = newfinefile + '.gz'

            # create new concat job for each case (each one uses it's own sub file)
            subloc = os.path.join(self.splinter_data_location[pitem][pifo][ff], 'concat.sub')
            finefiles = [finefiles] # make into a list (for rmnode below)

          # create new concat job for each case (each one uses it's own sub file)
          if subloc is not None:
            concatjob = concatJob(subfile=subloc, output=newfinefile, accgroup=self.accounting_group, accuser=self.accounting_group_user, logdir=self.log_dir)
            concatnode = concatNode(concatjob)
            concatnode.set_files(catfiles)
            concatnode.add_parent(parent)
            self.add_node(concatnode)

            self.concat_nodes[pitem][pifo][ff] = concatnode

            # make the processed file now just contain the final file location
            self.processed_files[pitem][pifo][ff] = [newfinefile]

          # remove original files
          if (len(finefiles) > 1 or self.engine == 'splinter') and concatnode != None:
            rmnode = removeNode(rmjob)

            if prevfile != None: # remove previous files
              finefiles.append(os.path.join(self.splinter_data_location[pitem][pifo][ff], prevfile[0]))

            rmnode.set_files(finefiles)
            rmnode.add_parent(concatnode) # only do after concatenation
            self.add_node(rmnode)


  def get_config_option(self, section, option, cftype=None, default=None, allownone=False):
    """
    Get a value of type cftype ('string', 'int', 'float', 'boolean', 'list', 'dict' or 'dir') from the configuration parser object.

    Return value on success and None on failure
    """

    value = None # return value for failure to parse option

    if cftype == None or cftype == 'string' or cftype == 'dir':
      try:
        value = self.config.get(section, option)
      except:
        if cftype != 'dir':
          if not allownone:
            if not isinstance(default, str):
              print("Error... could not parse '%s' option from '[%s]' section." % (option, section), file=sys.stderr)
              self.error_code = -1
            else:
              print("Warning... could not parse '%s' option from '[%s]' section. Defaulting to %s." % (option, section, default))
              value = default
          else: # check directory exists
            value = default
    elif cftype == 'float':
      try:
        value = self.config.getfloat(section, option)
      except:
        if not allownone:
          if not isinstance(default, float):
            print("Error... could not parse '%s' float option from '[%s]' section." % (option, section), file=sys.stderr)
            self.error_code = -1
          else:
            print("Warning... could not parse '%s' float option from '[%s]' section. Defaulting to %f." % (option, section, default))
            value = default
    elif cftype == 'boolean':
      try:
        value = self.config.getboolean(section, option)
      except:
        if not allownone:
          if not isinstance(default, bool):
            print("Error... could not parse '%s' boolean option from '[%s]' section." % (option, section), file=sys.stderr)
            self.error_code = -1
          else:
            print("Warning... could not parse '%s' boolean option from '[%s]' section. Defaulting to %r." % (option, section, default))
            value = default
    elif cftype == 'int':
      try:
        value = self.config.getint(section, option)
      except:
        if not allownone:
          if not isinstance(default, int):
            print("Error... could not parse '%s' int option from '[%s]' section." % (option, section), file=sys.stderr)
            self.error_code = -1
          else:
            print("Warning... could not parse '%s' int option from '[%s]' section. Defaulting to %d." % (option, section, default))
            value = default
    elif cftype == 'list':
      try:
        value = ast.literal_eval(self.config.get(section, option))
        if not isinstance(value, list):
          value = [value]
      except:
        if not allownone:
          if not instance(default, list):
            print("Error... could not parse '%s' list option from '[%s]' section." % (option, section), file=sys.stderr)
            self.error_code = -1
          else:
            print("Warning... could not parse '%s' list option from '[%s]' section. Defaulting to [%s]." % (option, section, ', '.join(default)))
            value = default
    elif cftype == 'dict':
      try:
        value = ast.literal_eval(self.config.get(section, option))

        if not isinstance(value, dict) and isinstance(default, dict):
          print("Warning... could not parse '%s' dictionary option from '[%s]' section. Defaulting to %s." % (option, section, str(default)))
          value = default
        elif not isinstance(value, dict) and not isinstance(default, dict):
          print("Error... could not parse '%s' dictionary option from '[%s]' section." % (option, section), file=sys.stderr)
          self.error_code = -1
      except:
        if not allownone:
          if not isinstance(default, dict):
            print("Error... could not parse '%s' dictionary option from '[%s]' section." % (option, section), file=sys.stderr)
            self.error_code = -1
          else:
            print("Warning... could not parse '%s' dictionary option from '[%s]' section. Defaulting to %s." % (option, section, str(default)))
            value = default
    else:
      print("Error... unknown trying to get unknown type '%s' from configuration file" % cftype, file=sys.stderr)
      self.error_code = -1

    return value


  def check_universe(self, universe):
    """
    Check Condor universe is 'local', 'vanilla' or 'standard'
    """
    if universe not in ['local', 'vanilla', 'standard']:
      return True
    else:
      return False


  def setup_datafind(self):
    """
    Create and setup the data find jobs.
    """

    # Create data find job
    self.cache_files = {}
    self.datafind_job = None
    if self.config.has_option('condor', 'datafind'):
      # check if a dictionary of ready made cache files has been given
      datafind = self.config.get('condor', 'datafind')

      if isinstance(datafind, dict):
        # check there is a file for each detector and that they exist
        for ifo in self.ifos:
          if ifo not in datafind:
            print("Warning... no frame/SFT cache file given for %s, try using system gw_data_find instead" % ifo)
            datafindexec = self.find_exec_file('gw_data_find')
            if datafindexec is None:
              print("Error... could not find 'gw_data_find' in your 'PATH'", file=sys.stderr)
              self.error_code = -1
              return
            else:
              self.config.set('condor', 'datafind', datafindexec) # set value in config file parser
          else:
            if not os.path.isfile(datafind[ifo]):
              print("Warning... frame/SFT cache file '%s' does not exist, try using system gw_data_find instead" % ifo)
              datafindexec = self.find_exec_file('gw_data_find')
              if datafindexec is None:
                print("Error... could not find 'gw_data_find' in your 'PATH'", file=sys.stderr)
                self.error_code = -1
                return
              else:
                self.config.set('condor', 'datafind', datafindexec) # set value in config file parser
            else:
              self.cache_files[ifo] = datafind[ifo]

        # check if a datafind job is needed for any of the detectors
        if len(self.cache_files) < len(self.ifos):
          self.datafind_job = pipeline.LSCDataFindJob(self.preprocessing_base_dir.values()[0], self.log_dir, self.config)
      else: # a data find exectable has been given
        if os.path.isfile(datafind) and os.access(datafind, os.X_OK):
          self.datafind_job = pipeline.LSCDataFindJob(self.preprocessing_base_dir.values()[0], self.log_dir, self.config)
        else:
          print("Warning... data find executable '%s' does not exist, or is not executable, try using system gw_data_find instead" % datafind)
          datafindexec = self.find_exec_file('gw_data_find')
          if datafindexec is None:
            print("Error... could not find 'gw_data_find' in your 'PATH'", file=sys.stderr)
            self.error_code = -1
            return
          else:
            cp.set('condor', 'datafind', datafindexec) # set value in config file parser
            self.datafind_job = pipeline.LSCDataFindJob(self.preprocessing_base_dir.values()[0], self.log_dir, self.config)
    else:
      # if no data find is specified try using the system gw_data_find
      datafindexec = self.find_exec_file('gw_data_find')
      if datafindexec is None:
        print("Error... could not find 'gw_data_find' in your 'PATH'", file=sys.stderr)
        self.error_code = -1
        return
      else:
        self.config.set('condor', 'datafind', datafindexec) # set value in config file parser
        self.datafind_job = pipeline.LSCDataFindJob(self.preprocessing_base_dir.values()[0], self.log_dir, self.config)

    # add additional options to data find job
    if self.datafind_job != None:
      self.datafind_job.add_condor_cmd('accounting_group', self.accounting_group)

      if self.accounting_group_user != None:
        self.datafind_job.add_condor_cmd('accounting_group_user', self.accounting_group_user)

    # reset the sub file location
    self.datafind_job.set_sub_file(os.path.join(self.run_dir, 'datafind.sub'))

    # Set gw_data_find nodes (one for each detector)
    if len(self.cache_files) < len(self.ifos):
      self.set_datafind_nodes()


  def set_datafind_nodes(self):
    """
    Add data find nodes to a dictionary of nodes
    """

    self.datafind_nodes = {}

    if self.config.has_option('datafind', 'type'):
      frtypes = ast.literal_eval(self.config.get('datafind', 'type'))

      if not isinstance(frtypes, dict):
        print("Error... the data find 'types' must be a dictionary of values for each detector", file=sys.stderr)
        self.error_code = -1
        return
    else:
      print("Error... no frame 'type' specified for data find", file=sys.stderr)
      self.error_code = -1
      return

    for ifo in self.ifos:
      if not ifo in frtypes:
        print("Error... no data find type for %s" % ifo, file=sys.stderr)
        self.error_code = -1
        return

      # check if cache file is already set for the given detector
      if ifo in self.cache_files:
        continue

      dfnode = pipeline.LSCDataFindNode(self.datafind_job)
      dfnode.set_observatory(ifo[0])
      dfnode.set_type(frtypes[ifo])
      dfnode.set_start(self.initial_start[ifo])
      dfnode.set_end(self.endtime[ifo])

      # reset the default LSCDataFindJob output cache filename
      cachefile = os.path.join(self.preprocessing_base_dir[ifo], 'cache.lcf')
      self.cache_files[ifo] = cachefile
      dfnode.set_output(cachefile)

      self.datafind_nodes[ifo] = dfnode
      self.add_node(dfnode) # add nodes into DAG


  def find_data_segments(self, starttime, endtime, ifo, outfile):
    """
    Find data segments and output them to an acsii text segment file containing the start and end times of
    each segment.
    """

    # check if segment file(s) is given
    segfile = self.get_config_option('segmentfind', 'seg_files', cftype='string', allownone=True) # check if file is given
    if segfile is None: # try getting dictionary
      segfiles = self.get_config_option('segmentfind', 'seg_files', cftype='dict', allownone=True)
      if segfiles is not None:
        if ifo not in segfiles:
          print("Error... No segment file given for '%s'" % ifo)
          self.error_code = -1
          return
        else:
          segfile = segfiles[ifo]

    if segfile is not None:
      # check segment file exists
      if not os.path.isfile(segfile):
        print("Error... segment file '%s' does not exist." % segfile)
        self.error_code = -1
        return
      else:
        # copy segment file to the 'outfile' location
        try:
          shutil.copyfile(segfile, outfile)
        except:
          print("Error... could not copy segment file to location of '%s'." % outfile)
          self.error_code = -1
        return # exit function

    # otherwise try and get the segment list
    # get server
    if self.config.has_option('segmentfind', 'server'):
      server = self.config.get('segmentfind', 'server')
    else:
      print("No segment server specified: defaulting to 'https://segments.ligo.org'")
      server = 'https://segments.ligo.org'

    # get segment types to include
    segmenttypes = self.get_config_option('segmentfind', 'segmenttype', cftype='dict')

    # get segment types to exclude
    excludesegs = self.get_config_option('segmentfind', 'excludetype', cftype='dict', allownone=True)

    # check segment types dictionary contains type for the given detector
    if ifo not in segmenttypes:
      print("Error... No segment type for %s" % ifo, file=sys.stderr)
      self.error_code = -1
      return

    segFindCall = ' '.join([self.config.get('segmentfind', 'segfind'),
                            '--segment-url', server,
                            '--query-segments',
                            '--include-segments', segmenttypes[ifo],
                            '--gps-start-time', str(starttime),
                            '--gps-end-time', str(endtime)])

    if excludesegs is not None:
      if ifo in excludesegs:
        if len(excludesegs[ifo]) > 0:
          segFindCall += ' --exclude-segments ' + excludesegs[ifo]

    xmlToTxtCall = ' '.join([self.config.get('segmentfind', 'ligolw_print'),
                             "--table segment --column start_time --column end_time --delimiter ' '",
                             ' > ', outfile])

    segCall = ' '.join([segFindCall, '|', xmlToTxtCall])

    print("Generating segments: " + segCall)

    p = sp.Popen(segCall, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
    out, err = p.communicate()

    if p.returncode != 0:
      print("Error... could not generate segment list. Call returned with error:", file=sys.stderr)
      print("\tstdout: %s" % out, file=sys.stderr)
      print("\tstderr: %s" % err, file=sys.stderr)
      self.error_code = -1
      return


  def find_exec_file(self, filename):
    """
    Search through the PATH environment for the first instance of the executable file "filename"
    """

    if os.path.isfile(filename) and os.access(filename, os.X_OK):
      return filename # already have the executable file

    # search through PATH environment variable
    for d in os.environ['PATH'].split(os.pathsep):
      filecheck = os.path.join(d, filename)
      if os.path.isfile(filecheck) and os.access(filecheck, os.X_OK):
        return filecheck

    return None


  def mkdirs(self, path):
    """
    Helper function. Make the given directory, creating intermediate
    dirs if necessary, and don't complain about it already existing.
    """
    if os.access(path,os.W_OK) and os.path.isdir(path): return
    else:
      try:
        os.makedirs(path)
      except:
        print("Error... cannot make directory '%s'" % path, file=sys.stderr)
        self.error_code = -1







class heterodyneJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A lalapps_heterodyne_pulsar job to heterodyne the data.
  """
  def __init__(self, execu, univ='vanilla', accgroup=None, accuser=None, logdir=None, rundir=None, subprefix='', requestmemory=None):
    self.__executable = execu
    self.__universe = univ
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    self.add_condor_cmd('getenv','True')

    if requestmemory is not None:
      if isinstance(requestmemory, int):
        self.add_condor_cmd('RequestMemory', requestmemory)

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'heterodyne-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'heterodyne-$(cluster).err'))
    else:
      self.set_stdout_file('heterodyne-$(cluster).out')
      self.set_stderr_file('heterodyne-$(cluster).err')

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, subprefix+'heterodyne.sub'))
    else:
      self.set_sub_file(subprefix+'heterodyne.sub')


class heterodyneNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  A heterodyneNode runs an instance of lalapps_heterodyne_pulsar in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of lalapps_heterodyne_pulsar
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    # initilise job variables
    self.__ifo = None
    self.__param_file = None
    self.__freq_factor = None
    self.__filter_knee = None
    self.__sample_rate = None
    self.__resample_rate = None
    self.__data_file = None
    self.__channel = None
    self.__seg_list = None
    self.__data_file = None
    self.__output_file = None
    self.__het_flag = None
    self.__pulsar = None
    self.__high_pass = None
    self.__scale_fac = None
    self.__manual_epoch = None
    self.__gzip = False

  def set_data_file(self,data_file):
    # set file containing data to be heterodyne (either list of frames or coarse het output)
    self.add_var_opt('data-file',data_file)
    self.__data_file = data_file

  def set_output_file(self,output_file):
    # set output directory
    self.add_var_opt('output-file',output_file)
    self.__output_file = output_file

  def set_seg_list(self,seg_list):
    # set segment list to be used
    self.add_var_opt('seg-file',seg_list)
    self.__seg_list = seg_list

  def set_ifo(self, ifo):
    # set detector
    self.add_var_opt('ifo', ifo)
    self.__ifo = ifo

  def set_param_file(self, param_file):
    # set pulsar parameter file
    self.add_var_opt('param-file', param_file)
    self.__param_file = param_file

  def set_freq_factor(self, freq_factor):
    # set the factor by which to muliply the pulsar spin frequency (normally 2.0)
    self.add_var_opt('freq-factor', freq_factor)
    self.__freq_factor = freq_factor

  def set_param_file_update(self, param_file_update):
    # set file containing updated pulsar parameters
    self.add_var_opt('param-file-update',param_file_update)

  def set_manual_epoch(self, manual_epoch):
      # set manual pulsar epoch
      self.add_var_opt('manual-epoch',manual_epoch)
      self.__manual_epoch = manual_epoch

  def set_ephem_earth_file(self, ephem_earth_file):
    # set the file containing the earth's ephemeris
    self.add_var_opt('ephem-earth-file', ephem_earth_file)

  def set_ephem_sun_file(self, ephem_sun_file):
    # set the file containing the sun's ephemeris
    self.add_var_opt('ephem-sun-file', ephem_sun_file)

  def set_ephem_time_file(self, ephem_time_file):
    # set the file containing the Einstein delay correction ephemeris
    self.add_var_opt('ephem-time-file', ephem_time_file)

  def set_pulsar(self,pulsar):
    # set pulsar name
    self.add_var_opt('pulsar',pulsar)
    self.__pulsar = pulsar

  def set_het_flag(self,het_flag):
    # set heterodyne flag
    self.add_var_opt('heterodyne-flag',het_flag)
    self.__het_flag = het_flag

  def set_filter_knee(self,filter_knee):
    # set filter knee frequency
    self.add_var_opt('filter-knee',filter_knee)
    self.__filter_knee = filter_knee

  def set_channel(self,channel):
    # set channel containing data from frames
    self.add_var_opt('channel',channel)
    self.__channel = channel

  def set_sample_rate(self,sample_rate):
    # set sample rate of input data
    self.add_var_opt('sample-rate',sample_rate)
    self.__sample_rate = sample_rate

  def set_resample_rate(self,resample_rate):
    # set resample rate for output data
    self.add_var_opt('resample-rate',resample_rate)
    self.__resample_rate = resample_rate

  def set_stddev_thresh(self,stddev_thresh):
    # set standard deviation threshold at which to remove outliers
    self.add_var_opt('stddev-thresh',stddev_thresh)

  def set_calibrate(self):
    # set calibration flag
    self.add_var_opt('calibrate', '') # no variable required

  def set_verbose(self):
    # set verbose flag
    self.add_var_opt('verbose', '') # no variable required

  def set_bininput(self):
    # set binary input file flag
    self.add_var_opt('binary-input', '') # no variable required

  def set_binoutput(self):
    # set binary output file flag
    self.add_var_opt('binary-output', '') # no variable required

  def set_gzip_output(self):
    # set gzipped output file flag
    self.add_var_opt('gzip-output', '') # no variable required
    self.__gzip = True

  def set_response_function(self,response_function):
    # set reponse function file
    self.add_var_opt('response-file',response_function)

  def set_coefficient_file(self,coefficient_file):
    # set the file containing the calibration coefficients (e.g alpha and gammas)
    self.add_var_opt('coefficient-file',coefficient_file)

  def set_sensing_function(self,sensing_function):
    # set file containing the sensing function for calibration
    self.add_var_opt('sensing-function',sensing_function)

  def set_open_loop_gain(self,open_loop_gain):
    # set file containing the open loop gain for calibration
    self.add_var_opt('open-loop-gain',open_loop_gain)

  def set_scale_fac(self,scale_fac):
    # set scale factor for calibrated data
    self.add_var_opt('scale-factor',scale_fac)

  def set_high_pass(self,high_pass):
    # set high-pass frequency for calibrated data
    self.add_var_opt('high-pass-freq',high_pass)


class splinterJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A lalapps_SplInter job to process SFT data.
  """
  def __init__(self, execu, univ='vanilla', accgroup=None, accuser=None, logdir=None, rundir=None):
    self.__executable = execu
    self.__universe = univ
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    self.add_condor_cmd('getenv','True')

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'splinter-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'splinter-$(cluster).err'))
    else:
      self.set_stdout_file('splinter-$(cluster).out')
      self.set_stderr_file('splinter-$(cluster).err')

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, 'splinter.sub'))
    else:
      self.set_sub_file('splinter.sub')


class splinterNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  A splinterNode runs an instance of lalapps_Splinter in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of lalapps_SplInter
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    # initilise job variables
    self.__ifo = None
    self.__param_file = None
    self.__param_dir = None
    self.__start_freq = None
    self.__end_freq = None
    self.__freq_factor = None
    self.__data_file = None
    self.__seg_list = None
    self.__sft_cache = None
    self.__sft_loc = None
    self.__output_dir = None
    self.__stddev_thresh = None
    self.__bandwidth = None
    self.__min_seg_length = None
    self.__starttime = None
    self.__endtime = None
    self.__ephem_dir = None
    self.__gzip = False

  def set_start_freq(self, f):
    # set the start frequency of the SFTs
    self.add_var_opt('start-freq', f)
    self.__start_freq = f

  def set_end_freq(self, f):
    # set the end frequency of the SFTs
    self.add_var_opt('end-freq', f)

  def set_sft_cache(self, f):
    # set file containing list of SFTs
    self.add_var_opt('sft-cache', f)
    self.__sft_cache = f

  def set_sft_loc(self, f):
    # set directory of files containing list of SFTs
    self.add_var_opt('sft-loc', f)
    self.__sft_loc = f

  def set_output_dir(self, f):
    # set output directory
    self.add_var_opt('output-dir', f)
    self.__output_dir = f

  def set_seg_list(self, f):
    # set segment list to be used
    self.add_var_opt('seg-file', f)
    self.__seg_list = f

  def set_ifo(self, ifo):
    # set detector
    self.add_var_opt('ifo', ifo)
    self.__ifo = ifo

  def set_param_file(self, f):
    # set pulsar parameter file
    self.add_var_opt('param-file', f)
    self.__param_file = f

  def set_param_dir(self, f):
    # set pulsar parameter directory
    self.add_var_opt('param-dir', f)
    self.__param_dir = f

  def set_freq_factor(self, f):
    # set the factor by which to muliply the pulsar spin frequency (normally 2.0)
    self.add_var_opt('freq-factor', f)
    self.__freq_factor = f

  def set_bandwidth(self, f):
    # set the bandwidth to use in the interpolation
    self.add_var_opt('bandwidth', f)
    self.__bandwidth = f

  def set_min_seg_length(self, f):
    # set the minimum science segment length to use
    self.add_var_opt('min-seg-length', f)
    self.__min_seg_length = f

  def set_ephem_dir(self, f):
    # set the directory containing the solar system ephemeris files
    self.add_var_opt('ephem-dir', f)
    self.__ephem_dir = f

  def set_stddev_thresh(self, f):
    # set standard deviation threshold at which to remove outliers
    self.add_var_opt('stddev-thresh', f)
    self.__stddev_thresh = f

  def set_gzip_output(self): # need to add this to Splinter
    # set gzipped output file flag
    self.add_var_opt('gzip-output', '') # no variable required
    self.__gzip = True

  def set_starttime(self, f):
    # set the start time of data to use
    self.add_var_opt('starttime', f)
    self.__starttime = f

  def set_endtime(self, f):
    # set the end time of data to use
    self.add_var_opt('endtime', f)
    self.__endtime = f


"""
  Job for concatenating processed (heterodyned or spectrally interpolated) files
"""
class concatJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A concatenation job (using "cat" and output to stdout - a new job is needed for each pulsar)
  """
  def __init__(self, subfile=None, output=None, accgroup=None, accuser=None, logdir=None):
    self.__executable = '/bin/cat' # use cat
    self.__universe = 'local' # use local as "cat" should not be compute intensive

    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    if subfile == None:
      print("Error... Condor sub file required for concatenation job", file=sys.stderr)
      sys.exit(1)
    else:
      self.set_sub_file(subfile)

    if output == None:
      print("Error... output file required for concatenation job", file=sys.stderr)
      sys.exit(1)
    else:
      self.set_stdout_file(output)

    if logdir != None:
      self.set_stderr_file(os.path.join(logdir, 'concat-$(cluster).err'))
    else:
      self.set_stderr_file('concat-$(cluster).err')

    self.add_arg('$(macrocatfiles)') # macro for input files to be concatenated


class concatNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  A node for a concatJob
  """

  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of parameter estimation code.
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    self.__files = None

  def set_files(self, files):
    # set the files to be concatenated ("files" is a list of files to be concatenated)
    self.add_macro('macrocatfiles', " ".join(files))
    self.__files = files


"""
  Job for removing files
"""
class removeJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A remove job (using "rm" to remove files)
  """
  def __init__(self, accgroup=None, accuser=None, logdir=None, rundir=None):
    self.__executable = "/bin/rm"  # use "rm"
    self.__universe = "local"      # rm should not be compute intensive, so use local universe

    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'rm-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'rm-$(cluster).err'))
    else:
      self.set_stdout_file('rm-$(cluster).out')
      self.set_stderr_file('rm-$(cluster).err')

    self.add_arg('-f $(macrormfiles)') # macro for input files to be removed (use "-f" to force removal)

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, 'rm.sub'))
    else:
      self.set_sub_file('rm.sub')


class removeNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  An instance of a removeJob in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of rm.
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    self.__files = None

  def set_files(self, files):
    # set file(s) to be removed, where "files" is a list containing all files
    self.add_macro('macrormfiles', " ".join(files))
    self.__files = files


"""
  Job for moving files
"""
class moveJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A move job (using "mv" to move files)
  """
  def __init__(self, accgroup=None, accuser=None, logdir=None, rundir=None):
    self.__executable = "/bin/mv"  # use "mv"
    self.__universe = "local"      # mv should not be compute intensive, so use local universe

    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'mv-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'mv-$(cluster).err'))
    else:
      self.set_stdout_file('mv-$(cluster).out')
      self.set_stderr_file('mv-$(cluster).err')

    self.add_arg('$(macrosource) $(macrodestination)') # macro for source and destination files

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, 'mv.sub'))
    else:
      self.set_sub_file('mv.sub')


class moveNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  An instance of a moveJob in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of mv.
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    self.__sourcefile = None
    self.__destinationfile = None

  def set_source(self, sfile):
    # set file to be moved
    self.add_macro('macrosource', sfile)
    self.__sourcefiles = sfile

  def set_destination(self, dfile):
    # set destination of file to be moved
    self.add_macro('macrodestination', dfile)
    self.__destinationfile = dfile


"""
  Pulsar parameter estimation pipeline utilities
"""
class ppeJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A parameter estimation job
  """
  def __init__(self, execu, univ='vanilla', accgroup=None, accuser=None, logdir=None, rundir=None):
    self.__executable = execu
    self.__universe = univ
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    self.add_condor_cmd('getenv','True')

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'ppe-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'ppe-$(cluster).err'))
    else:
      self.set_stdout_file('ppe-$(cluster).out')
      self.set_stderr_file('ppe-$(cluster).err')

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, 'ppe.sub'))
    else:
      self.set_sub_file('ppe.sub')

    self.add_arg('$(macroargs)') # macro for additional command line arguments that will not alway be used


class ppeNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  A pes runs an instance of the parameter estimation code in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of parameter estimation code.
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    # initilise job variables
    self.__detectors = None
    self.__par_file = None
    self.__cor_file = None
    self.__input_files = None
    self.__outfile = None
    self.__chunk_min = None
    self.__chunk_max = None
    self.__psi_bins = None
    self.__time_bins = None
    self.__prior_file = None
    self.__ephem_earth = None
    self.__ephem_sun = None
    self.__ephem_time = None
    self.__harmonics = None
    self.__biaxial = False
    self.__gaussian_like = False
    self.__randomise = None

    self.__Nlive = None
    self.__Nmcmc = None
    self.__Nmcmcinitial = None
    self.__Nruns = None
    self.__tolerance = None
    self.__randomseed = None

    self.__use_roq = False
    self.__roq_ntraining = None
    self.__roq_tolerance = None
    self.__roq_uniform = False
    self.__roq_output_weights = None
    self.__roq_input_weights = None

    self.__temperature = None
    self.__ensmeble_walk = None
    self.__ensemble_stretch = None
    self.__diffev = None

    self.__inject_file = None
    self.__inject_output = None
    self.__fake_data = None
    self.__fake_psd = None
    self.__fake_starts = None
    self.__fake_lengths = None
    self.__fake_dt = None
    self.__scale_snr = None

    self.__sample_files = None
    self.__sample_nlives = None
    self.__prior_cell = None

    # legacy inputs
    self.__oldChunks = None
    self.__sourceModel = False

    self.__verbose = False

    # set macroargs to be empty
    self.add_macro('macroargs', '')

  def set_detectors(self,detectors):
    # set detectors
    self.add_var_opt('detectors',detectors)
    self.__detectors = detectors

  def set_verbose(self):
    # set to run code in verbose mode
    self.add_var_opt('verbose', '')
    self.__verbose = True

  def set_par_file(self,parfile):
    # set pulsar parameter file
    self.add_var_opt('par-file',parfile)
    self.__par_file = parfile

  def set_cor_file(self,corfile):
    # set pulsar parameter correlation matrix file

    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --cor-file ' + corfile
    self.add_macro('macroargs', curmacroval)
    # self.add_var_opt('cor-file',corfile)
    self.__cor_file = corfile

  def set_input_files(self, inputfiles):
    # set data files for analysing
    self.add_var_opt('input-files', inputfiles)
    self.__input_files = inputfiles

  def set_outfile(self, of):
    # set the output file
    self.add_var_opt('outfile', of)
    self.__outfile = of

  def set_chunk_min(self, cmin):
    # set the minimum chunk length
    self.add_var_opt('chunk-min',cmin)
    self.__chunk_min = cmin

  def set_chunk_max(self, cmax):
    # set the maximum chunk length
    self.add_var_opt('chunk-max', cmax)
    self.__chunk_max = cmax

  def set_psi_bins(self, pb):
    # set the number of bins in psi for the psi vs time lookup table
    self.add_var_opt('psi-bins', pb)
    self.__psi_bins = pb

  def set_time_bins(self, tb):
    # set the number of bins in time for the psi vs time lookup table
    self.add_var_opt('time-bins',tb)
    self.__time_bins = tb

  def set_prior_file(self,pf):
    # set the prior ranges file
    self.add_var_opt('prior-file',pf)
    self.__prior_file = pf

  def set_ephem_earth(self,ee):
    # set earth ephemeris file
    self.add_var_opt('ephem-earth',ee)
    self.__ephem_earth = ee

  def set_ephem_sun(self,es):
    # set sun ephemeris file
    self.add_var_opt('ephem-sun',es)
    self.__ephem_sun = es

  def set_ephem_time(self,et):
    # set time correction ephemeris file
    self.add_var_opt('ephem-time',et)
    self.__ephem_time = et

  def set_harmonics(self,h):
    # set model frequency harmonics
    self.add_var_opt('harmonics',h)
    self.__harmonics = h

  def set_Nlive(self,nl):
    # set number of live points
    self.add_var_opt('Nlive',nl)
    self.__Nlive = nl

  def set_Nmcmc(self,nm):
    # set number of MCMC iterations
    self.add_var_opt('Nmcmc',nm)
    self.__Nmcmc = nm

  def set_Nmcmcinitial(self,nm):
    # set number of MCMC iterations
    self.add_var_opt('Nmcmcinitial',nm)
    self.__Nmcmcinitial = nm

  def set_Nruns(self,nr):
    # set number of internal nested sample runs
    self.add_var_opt('Nruns',nr)
    self.__Nruns = nr

  def set_tolerance(self, tol):
    # set tolerance criterion for finishing nested sampling
    self.add_var_opt('tolerance', tol)
    self.__tolerance = tol

  def set_randomseed(self, rs):
    # set random number generator seed
    self.add_var_opt('randomseed', rs)
    self.__randomseed = rs

  def set_ensemble_stretch(self, f):
    # set the fraction of time to use ensemble stretch moves as proposal
    self.add_var_opt('ensembleStretch', f)
    self.__ensemble_stretch = f

  def set_ensemble_walk(self, f):
    # set the fraction of time to use ensemble walk moves as proposal
    self.add_var_opt('ensembleWalk', f)
    self.__ensemble_walk = f

  def set_temperature(self, temp):
    # set temperature scale for covariance proposal
    self.add_var_opt('temperature', temp)
    self.__temperature = temp

  def set_diffev(self,de):
    # set fraction of time to use differential evolution as proposal
    self.add_var_opt('diffev',de)
    self.__diffev = de

  def set_inject_file(self,ifil):
    # set a pulsar parameter file from which to make an injection
    self.add_var_opt('inject-file',ifil)
    self.__inject_file = ifil

  def set_inject_output(self,iout):
    # set filename in which to output the injected signal
    self.add_var_opt('inject-output',iout)
    self.__inject_output = iout

  def set_fake_data(self,fd):
    # set the detectors from which to generate fake data
    self.add_var_opt('fake-data',fd)
    self.__fake_data = fd

  def set_fake_psd(self,fp):
    # set the PSDs of the fake data
    self.add_var_opt('fake-psd',fp)
    self.__fake_psd = fp

  def set_fake_starts(self,fs):
    # set the start times of the fake data
    self.add_var_opt('fake-starts',fs)
    self.__fake_starts = fs

  def set_fake_lengths(self,fl):
    # set the lengths of the fake data
    self.add_var_opt('fake-lengths',fl)
    self.__fake_lengths = fl

  def set_fake_dt(self,fdt):
    # set the sample interval of the fake data
    self.add_var_opt('fake-dt',fdt)
    self.__fake_dt = fdt

  def set_scale_snr(self,ssnr):
    # set the SNR of the injected signal
    self.add_var_opt('scale-snr',ssnr)
    self.__scale_snr = ssnr

  def set_scale_snr(self,ssnr):
    # set the SNR of the injected signal
    self.add_var_opt('scale-snr',ssnr)
    self.__scale_snr = ssnr

  def set_sample_files(self,ssf):
    # set the nested sample files to be used as a prior
    self.add_var_opt('sample-files',ssf)
    self.__sample_files = ssf

  def set_sample_nlives(self,snl):
    # set the number of live points for the nested sample files
    self.add_var_opt('sample-nlives',snl)
    self.__sample_nlives = snl

  def set_prior_cell(self,pc):
    # set the k-d tree cell size for the prior
    self.add_var_opt('prior-cell',pc)
    self.__prior_cell = pc

  def set_OldChunks(self):
    # use the old data segmentation routine i.e. 30 min segments
    self.add_var_opt('oldChunks', '')
    self.__oldChunks = True

  def set_source_model(self):
    # use the physical parameter model from Jones

    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --source-model'
    self.add_macro('macroargs', curmacroval)
    self.__sourceModel = True

  def set_biaxial(self):
    # the model is a biaxial star using the amplitude/phase waveform parameterisation

    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --biaxial'
    self.add_macro('macroargs', curmacroval)
    self.__biaxial = True

  def set_gaussian_like(self):
    # use a Gaussian likelihood rather than the Students-t likelihood
    self.add_var_opt('gaussian-like', '')
    self.__gaussian_like = True

  def set_randomise(self, f):
    # set flag to randomise the data times stamps for "background" analyses

    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --randomise ' + f
    self.add_macro('macroargs', curmacroval)
    self.__randomise = f

  def set_roq(self):
    # set to use Reduced Order Quadrature (ROQ)

    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --roq'
    self.add_macro('macroargs', curmacroval)
    self.__use_roq = True

  def set_roq_ntraining(self, f):
    # set the number of training waveforms to use in ROQ basis generation
    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --ntraining ' + f
    self.add_macro('macroargs', curmacroval)
    self.__roq_ntraining = f

  def set_roq_tolerance(self, f):
    # set the tolerance to use in ROQ basis generation
    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --roq-tolerance ' + f
    self.add_macro('macroargs', curmacroval)
    self.__roq_tolerance = f

  def set_roq_uniform(self):
    # set to use uniform distributions when sprinkling (phase) parameters for ROQ training basis generation
    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --roq-uniform'
    self.add_macro('macroargs', curmacroval)
    self.__roq_uniform = True

  def set_roq_inputweights(self,f):
    # set the location of the file containing pregenerated ROQ interpolants
    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --input-weights ' + f
    self.add_macro('macroargs', curmacroval)
    self.__roq_input_weights = f

  def set_roq_outputweights(self,f):
    # set the location of the file to output ROQ interpolants
    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --output-weights ' + f
    self.add_macro('macroargs', curmacroval)
    self.__roq_output_weights = f

  def set_roq_chunkmax(self,f):
    # set the maximum chunk length for if using ROQ (just adding using the chunk-max argument)
    # add this into the generic 'macroargs' macro as it is not a value that is always required
    if 'macroargs' in self.get_opts():
      curmacroval = self.get_opts()['macroargs']
    else:
      curmacroval = ''
    curmacroval = curmacroval + ' --chunk-max ' + f
    self.add_macro('macroargs', curmacroval)
    self.__chunk_max = int(f)


"""
  Job for creating the result page for a particular source
"""
class resultpageJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  def __init__(self, execu, univ='local', accgroup=None, accuser=None, logdir=None, rundir=None):
    self.__executable = execu
    self.__universe = univ
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    self.add_condor_cmd('getenv','True')

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'resultpage-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'resultpage-$(cluster).err'))
    else:
      self.set_stdout_file('resultpage-$(cluster).out')
      self.set_stderr_file('resultpage-$(cluster).err')

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, 'resultpage.sub'))
    else:
      self.set_sub_file('resultpage.sub')

    self.add_arg('$(macroconfigfile)') # macro for input configuration file


class resultpageNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  A resultpageNode runs an instance of the result page script in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of lalapps_knope_result_page
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    self.__configfile = None

  def set_config(self, configfile):
    self.add_macro('macroconfigfile', configfile)
    self.__configfile = configfile


"""
  Job for creating the collated results page for all sources
"""
class collateJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  def __init__(self, execu, univ='local', accgroup=None, accuser=None, logdir=None, rundir=None):
    self.__executable = execu
    self.__universe = univ
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    self.add_condor_cmd('getenv','True')

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'collate-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'collate-$(cluster).err'))
    else:
      self.set_stdout_file('collate-$(cluster).out')
      self.set_stderr_file('collate-$(cluster).err')

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, 'collate.sub'))
    else:
      self.set_sub_file('collate.sub')

    self.add_arg('$(macroconfigfile)') # macro for input configuration file


class collateNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  A collateNode runs an instance of the result page collation script in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an instance of lalapps_knope_collate_results
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    self.__configfile = None

  def set_config(self, configfile):
    self.add_macro('macroconfigfile', configfile)
    self.__configfile = configfile


class nest2posJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A merge nested sampling files job to use lalapps_nest2pos
  """
  def __init__(self, execu, univ='local', accgroup=None, accuser=None, logdir=None, rundir=None):
    self.__executable = execu
    self.__universe  = univ
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    if accgroup != None: self.add_condor_cmd('accounting_group', accgroup)
    if accuser != None: self.add_condor_cmd('accounting_group_user', accuser)

    self.add_condor_cmd('getenv','True')

    # set log files for job
    if logdir != None:
      self.set_stdout_file(os.path.join(logdir, 'n2p-$(cluster).out'))
      self.set_stderr_file(os.path.join(logdir, 'n2p-$(cluster).err'))
    else:
      self.set_stdout_file('n2p-$(cluster).out')
      self.set_stderr_file('n2p-$(cluster).err')

    self.add_arg('$(macroinputfiles)') # macro for input nested sample files

    if rundir != None:
      self.set_sub_file(os.path.join(rundir, 'n2p.sub'))
    else:
      self.set_sub_file('n2p.sub')


class nest2posNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
  A nest2posNode runs a instance of the lalapps_nest2pos to combine individual nested
  sample files in a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run an of the nested sample combination script
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    # initilise job variables
    self.__nest_files = None
    self.__nest_live = None
    self.__outfile = None
    self.__header = None
    self.__npos = None
    self.__gzip = False

  def set_nest_files(self,nestfiles):
    # set all the nested sample files
    self.__nest_files = nestfiles

    fe = os.path.splitext(nestfiles[0])[-1].lower()
    # set header file (only if not using hdf5 output)
    if fe != '.hdf' and fe != '.h5':
      header = nestfiles[0].rstrip('.gz')+'_params.txt'
      self.__header = header
      self.add_var_opt('headers', header)
    self.add_macro('macroinputfiles', ' '.join(nestfiles))

  def set_nest_live(self,nestlive):
    # set the number of live points from each file
    self.add_var_opt('Nlive',nestlive)
    self.__nest_live = nestlive

  def set_outfile(self,outfile):
    # set the output file for the posterior file
    self.add_var_opt('pos', outfile)
    self.__outfile = outfile

  def set_numpos(self, npos):
    # set the number of posterior samples for the posterior file
    self.add_var_opt('npos', npos)
    self.__npos = npos

  def set_gzip(self):
    self.add_var_opt('gzip', '')
    self.__gzip = True


# DEPRECATED
class createresultspageJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A job to create an individual pulsar results page
  """
  def __init__(self,execu,logpath,accgroup,accuser):
    self.__executable = execu
    self.__universe  = 'vanilla'
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    self.add_condor_cmd('getenv','True')
    self.add_condor_cmd('accounting_group', accgroup)
    self.add_condor_cmd('accounting_group_user', accuser)

    self.set_stdout_file(logpath+'/create_results_page-$(cluster).out')
    self.set_stderr_file(logpath+'/create_results_page-$(cluster).err')
    self.set_sub_file('create_results_page.sub')

    # additional required args
    self.add_arg('$(macrom)') # macro for MCMC directories
    self.add_arg('$(macrobk)') # macro for Bk (fine heterodyne file) directories
    self.add_arg('$(macroi)') # macro for IFOs
    self.add_arg('$(macrof)') # macro for nested sampling files
    self.add_arg('$(macrow)') # macro to say if a hardware injection
    self.add_arg('$(macros)') # macro to say if a software injection

class createresultspageNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
    A createresultspage node to run as part of a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run the segment list finding script
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    # initilise job variables
    self.__outpath = None
    self.__domcmc = False
    self.__mcmcdirs = []
    self.__donested = False
    self.__nestedfiles = []
    self.__parfile = None
    self.__Bkfiles = []
    self.__priorfile = None
    self.__ifos = []
    self.__histbins = None
    self.__epsout = False

  def set_outpath(self,val):
    # set the detector
    self.add_var_opt('o', val, short=True)
    self.__outpath = val
  def set_domcmc(self):
    # set to say using MCMC chains as input
    self.add_var_opt('M', '', short=True)
    self.__domcmc = True
  def set_mcmcdir(self,val):
    # set the MCMC file directories
    macroval = ''
    for f in val:
      macroval = '%s-m %s ' % (macroval, f)

    self.add_macro('macrom', macroval)
    self.add_macro('macrof', '') # empty macro for nested files
    self.__mcmcdirs = val
  def set_donested(self):
    # set to say using nested sampling results as input
    self.add_var_opt('nested', '')
    self.__donested = True
  def set_nestedfiles(self,val):
    # set the nested sampling files
    macroval = ''
    for f in val:
      macroval = '%s-f %s ' % (macroval, f)

    self.add_macro('macrof', macroval)
    self.add_macro('macrom', '') # empty macro for mcmc directories
    self.__nestedfiles = val
  def set_parfile(self,val):
    # set the pulsar parameter file
    self.add_var_opt('p', val, short=True)
    self.__parfile = val
  def set_bkfiles(self,val):
    # set the fine heterodyned data files
    macroval = ''
    for f in val:
      macroval = '%s-b %s ' % (macroval, f)

    self.add_macro('macrobk', macroval)
    self.__Bkfiles = val
  def set_priordir(self,val):
    # set the prior file directory
    self.add_var_opt('r', val, short=True)
    self.__priordir = None
  def set_ifos(self,val):
    # set the IFOs to analyse
    macroval = ''
    for f in val:
      macroval = '%s-i %s ' % (macroval, f)

    self.add_macro('macroi', macroval)
    self.__ifos = val
  def set_histbins(self,val):
    # set the number of histogram bins
    self.add_var_opt('n', val, short=True)
    self.__histbins = val
  def set_epsout(self):
    # set to output eps figs
    self.add_var_opt('e', '', short=True)
    self.__epsout = True
  def set_swinj(self, isswinj):
    # set to say that analysing software injection
    if isswinj:
      self.add_macro('macros', '--sw-inj')
    else:
      self.add_macro('macros', '')
  def set_hwinj(self, ishwinj):
    # set to say that analysing hardware injection
    if ishwinj:
      self.add_macro('macrow', '--hw-inj')
    else:
      self.add_macro('macrow', '')

class collateresultsJob(pipeline.CondorDAGJob, pipeline.AnalysisJob):
  """
  A job to collate all the individual pulsar results pages
  """
  def __init__(self,execu,logpath,accgroup,accuser):
    self.__executable = execu
    self.__universe  = 'vanilla'
    pipeline.CondorDAGJob.__init__(self, self.__universe, self.__executable)
    pipeline.AnalysisJob.__init__(self, None)

    self.add_condor_cmd('getenv','True')
    self.add_condor_cmd('accounting_group', accgroup)
    self.add_condor_cmd('accounting_group_user', accuser)

    self.set_stdout_file(logpath+'/collate_results-$(cluster).out')
    self.set_stderr_file(logpath+'/collate_results-$(cluster).err')
    self.set_sub_file('collate_results.sub')

    # some required argument macros
    self.add_arg('$(macroifo)') # for IFOs
    #self.add_arg('$(macrou)') # for output upper limits
    #self.add_arg('$(macron)') # for output pulsar values

class collateresultsNode(pipeline.CondorDAGNode, pipeline.AnalysisNode):
  """
    A collateresults node to run as part of a condor DAG.
  """
  def __init__(self,job):
    """
    job = A CondorDAGJob that can run the segment list finding script
    """
    pipeline.CondorDAGNode.__init__(self,job)
    pipeline.AnalysisNode.__init__(self)

    # initilise job variables
    self.__outpath = None
    self.__inpath = None
    self.__parfile = None
    self.__compilelatex = False
    self.__sorttype = None
    self.__ifos = []
    self.__outputlims = []
    self.__outputvals = []
    self.__outputhist = False
    self.__outputulplot = False
    self.__withprior = False
    self.__epsout = False

  def set_outpath(self,val):
    # set the detector
    self.add_var_opt('o', val, short=True)
    self.__outpath = val
  def set_inpath(self,val):
    # set the input path
    self.add_var_opt('z', val, short=True)
    self.__inpath = val
  def set_parfile(self,val):
    # set the pulsar parameter file directory
    self.add_var_opt('p', val, short=True)
    self.__parfile = val
  def set_compilelatex(self):
    # set to compile LaTeX results table
    self.add_var_opt('l', '', short=True)
    self.__compilelatex = True
  def set_sorttype(self,val):
    # set the sorting order of the output results
    self.add_var_opt('s', val, short=True)
    self.__sorttype = val
  def set_ifos(self,val):
    # set the list if IFOs to output results for
    macroval = ''
    for f in val:
      macroval = '%s-i %s ' % (macroval, f)

    self.add_macro('macroifo', macroval)
    self.__ifos = val
  def set_outputlims(self,val):
    # set the upper limit results to output
    macroval = ''
    for f in val:
      macroval = '%s-u %s ' % (macroval, f)

    self.add_macro('macrou', macroval)
    self.__outputlims = val
  def set_outputvals(self,val):
    # set the pulsar parameter values to output
    macroval = ''
    for f in val:
      macroval = '%s-n %s ' % (macroval, f)

    self.add_macro('macron', macroval)
    self.__outputvals = val
  def set_outputhist(self):
    # set to output histograms of the results
    self.add_var_opt('k', '', short=True)
    self.__outputhist = True
  def set_outputulplot(self):
    # set to output a plot of the ULs
    self.add_var_opt('t', '', short=True)
    self.__outputulplot = True
  def set_withprior(self):
    # set to output prior values with the hist and UL plots
    self.add_var_opt('w', '', short=True)
    self.__withprior = True
  def set_epsout(self):
    # set to output plots in eps format as well as png
    self.add_var_opt('e', '', short=True)
    self.__epsout = True
