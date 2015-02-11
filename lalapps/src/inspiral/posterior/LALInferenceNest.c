/* 
 *  InferenceNest.c:  Nested Sampling using LALInference
 *
 *  Copyright (C) 2009 Ilya Mandel, Vivien Raymond, Christian Roever, Marc van der Sluys and John Veitch
 *
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with with program; see the file COPYING. If not, write to the
 *  Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
 *  MA  02111-1307  USA
 */


#include <stdio.h>
#include <lal/Date.h>
#include <lal/GenerateInspiral.h>
#include <lal/LALInference.h>
#include <lal/FrequencySeries.h>
#include <lal/Units.h>
#include <lal/StringInput.h>
#include <lal/LIGOLwXMLInspiralRead.h>
#include <lal/TimeSeries.h>
#include <lalapps.h>
#include <lal/LALInferenceNestedSampler.h>
#include <lal/LALInferencePrior.h>
#include <lal/LALInferenceReadData.h>
#include <lal/LALInferenceLikelihood.h>
#include <lal/LALInferenceReadBurstData.h>
#include <lal/LALInferenceTemplate.h>
#include <lal/LALInferenceProposal.h>
#include <lal/LIGOLwXMLBurstRead.h>
#include <lal/GenerateBurst.h>
#include <lal/LALSimBurst.h>
#include <lal/LALInferenceInit.h>
#include <lal/LALInferenceCalibrationErrors.h>

LALInferenceRunState *initialize(ProcessParamsTable *commandLine);
void initializeNS(LALInferenceRunState *runState);
//void initVariables(LALInferenceRunState *state);

//void initStudentt(LALInferenceRunState *state);
// static void mc2masses(double mc, double eta, double *m1, double *m2);
void initializeMalmquistPrior(LALInferenceRunState *runState);
void LogNSSampleAsMCMCSampleToArray(LALInferenceRunState *state, LALInferenceVariables *vars);                             
void LogNSSampleAsMCMCSampleToFile(LALInferenceRunState *state, LALInferenceVariables *vars);                              

void LogNSSampleAsMCMCSampleToArray(LALInferenceRunState *state, LALInferenceVariables *vars)
{
  NSFillMCMCVariables(vars,state->priorArgs);
  LALInferenceLogSampleToArray(state, vars);
  return;
}

void LogNSSampleAsMCMCSampleToFile(LALInferenceRunState *state, LALInferenceVariables *vars)
{
  NSFillMCMCVariables(vars,state->priorArgs);
  LALInferenceLogSampleToFile(state, vars);
  return;
}

LALInferenceRunState *initialize(ProcessParamsTable *commandLine)
/* calls the "ReadData()" function to gather data & PSD from files, */
/* and initializes other variables accordingly.                     */
{
	char help[]="\
Initialisation arguments:\n\
(--verbose [N])\tOutput more info. N=1: errors, N=2 (default): warnings, N=3: info \n\
(--resume)\tAllow non-condor checkpointing every 4 hours. If give will check for OUTFILE_resume and continue if possible\n\n";
	LALInferenceRunState *irs=NULL;
	ProcessParamsTable *ppt=NULL;
	unsigned long int randomseed;
	struct timeval tv;
	FILE *devrandom;
	
	irs = XLALCalloc(1, sizeof(LALInferenceRunState));
	irs->commandLine=commandLine;
	
	/* Initialise parameters structure */
	irs->algorithmParams=XLALCalloc(1,sizeof(LALInferenceVariables));
	irs->priorArgs=XLALCalloc(1,sizeof(LALInferenceVariables));
	irs->proposalArgs=XLALCalloc(1,sizeof(LALInferenceVariables));
	
	INT4 verbose=0;
	INT4 x=0;
	ppt=LALInferenceGetProcParamVal(commandLine,"--verbose");
	if(ppt) {
	  if(ppt->value){
	    x=atoi(ppt->value);
	    switch(x){
	     case 0:
	       verbose=LALNDEBUG; /* Nothing */
	       break;
	     case 1:
	       verbose=LALMSGLVL1; /* Only errors */
	       break;
	     case 2:
	       verbose=LALMSGLVL2; /* Errors and warnings */
	       break;
	     case 3:
	       verbose=LALMSGLVL3; /* Errors, warnings and info */
	       break;
	     default:
	       verbose=LALMSGLVL2;
	       break;
	   }
	  }
	  else verbose=LALMSGLVL2; /* Errors and warnings */
	  LALInferenceAddVariable(irs->algorithmParams,"verbose", &verbose , LALINFERENCE_INT4_t,
				  LALINFERENCE_PARAM_FIXED);		
	}
	
  /*This is in common for both CBC and burst injections */
	LALInferenceCheckOptionsConsistency(commandLine);
  /* read data from files: */
	fprintf(stdout, " readData(): started.\n");

	irs->data = LALInferenceReadData(commandLine);

	/* (this will already initialise each LALIFOData's following elements:  */
  ppt=LALInferenceGetProcParamVal(commandLine,"--help");
  if(ppt)
  {
    fprintf(stdout,"%s",help);
    return(irs);
  }

	/*     fLow, fHigh, detector, timeToFreqFFTPlan, freqToTimeFFTPlan,     */
	/*     window, oneSidedNoisePowerSpectrum, timeDate, freqData         ) */
	fprintf(stdout, " LALInferenceReadData(): finished.\n");
	if (irs->data != NULL) {
    fprintf(stdout, " initialize(): successfully read data.\n");
    ppt=LALInferenceGetProcParamVal(commandLine,"--inj");
    if(ppt){
      INT4 errnum_pre,errnum_post;
      SimInspiralTable *inspiralTable=NULL;
      SimBurst *burstTable=NULL;
      
      /* The following is ugly, take a seat...
       * In order to avoid having to use a different option for burst and cbc injfile (which I did in the past) I will just take advantage of the fact that XLALSimBurstTableFromLIGOLw won't exit the code if the table is not a sim_burst table. If an injtable (of any kind) has been passed I will first try to call XLALSimBurstTableFromLIGOLw and then SimInspiralTableFromLIGOLw.
       * 
       * The output from these two calls is used just below to check which injection routine should be called (inspiral or burst). 
       * 
       * The problem with this is that XLALSimBurstTableFromLIGOLw will set the global variable xlalErrnoGlobal to a non zero status, making the call to fail the first time it checks it (which doesn't happen often, suprisingly enough).
       * 
       * I will thus re-set the error number to XLAL_SUCCESS after the two calls, after cheking that it was XLAL_SUCCESS before the calls.
       * 
       * I know, it's ugly. 
       * 
       * */
      errnum_pre = *XLALGetErrnoPtr();
      burstTable=XLALSimBurstTableFromLIGOLw(ppt->value,0,0);
      SimInspiralTableFromLIGOLw(&inspiralTable,ppt->value,0,0);    
      errnum_post = *XLALGetErrnoPtr();
      if (errnum_post != XLAL_SUCCESS && errnum_pre==XLAL_SUCCESS) 
        XLALSetErrno(XLAL_SUCCESS);

      if(burstTable){
        fprintf(stdout, " LALInferenceInjectBurstSignal(): started.\n");
        LALInferenceInjectBurstSignal(irs->data,commandLine);
        fprintf(stdout, " LALInferenceInjectBurstSignal(): finished.\n");
      }
      else if (inspiralTable){
        fprintf(stdout, " LALInferenceInjectInspiralSignal(): started.\n");
        LALInferenceInjectInspiralSignal(irs->data,commandLine);
        fprintf(stdout, " LALInferenceInjectInspiralSignal(): finished.\n");
      }
    }
    ppt=LALInferenceGetProcParamVal(commandLine,"--inject_from_mdc");
    if (ppt){
      fprintf(stdout,"WARNING: Injecting a signal from MDC has not been carefully tested yet! \n"); 
      LALInferenceInjectFromMDC(commandLine, irs->data);
    }
    irs->currentLikelihood=LALInferenceNullLogLikelihood(irs->data);
      
    printf("Injection Null Log Likelihood: %g\n", irs->currentLikelihood);
	}
	else
	{
		fprintf(stdout, " initialize(): no data read.\n");
		exit(1);
	}
	/* set up GSL random number generator: */
	gsl_rng_env_setup();
	irs->GSLrandom = gsl_rng_alloc(gsl_rng_mt19937);
	/* (try to) get random seed from command line: */
	ppt = LALInferenceGetProcParamVal(commandLine, "--randomseed");
	if (ppt != NULL)
		randomseed = atoi(ppt->value);
	else { /* otherwise generate "random" random seed: */
		if ((devrandom = fopen("/dev/random","r")) == NULL) {
			gettimeofday(&tv, 0);
			randomseed = tv.tv_sec + tv.tv_usec;
		} 
		else {
			if(1!=fread(&randomseed, sizeof(randomseed), 1, devrandom)){
			  fprintf(stderr,"Error: Unable to read random seed from /dev/random\n");
			  exit(1);
			}
			fclose(devrandom);
		}
	}
	fprintf(stdout, " initialize(): random seed: %lu\n", randomseed);
	gsl_rng_set(irs->GSLrandom, randomseed);
	return(irs);
}

void initializeMalmquistPrior(LALInferenceRunState *runState)
{
  
  REAL8 malmquist_loudest = 0.0;
  REAL8 malmquist_second_loudest = 5.0;
  REAL8 malmquist_network = 0.0;
  ProcessParamsTable *commandLine=runState->commandLine;
  ProcessParamsTable *ppt=NULL;
  
  ppt=LALInferenceGetProcParamVal(commandLine,"--malmquist-loudest-snr");
  if(ppt)
    malmquist_loudest = atof(ppt->value);
  ppt=LALInferenceGetProcParamVal(commandLine,"--malmquist-second-loudest-snr");
  if(ppt)
    malmquist_second_loudest = atof(ppt->value);
  ppt=LALInferenceGetProcParamVal(commandLine,"--malmquist-network-snr");
  if(ppt)
    malmquist_network = atof(ppt->value);
  LALInferenceAddVariable(runState->priorArgs, "malmquist_loudest_snr", &malmquist_loudest, LALINFERENCE_REAL8_t, LALINFERENCE_PARAM_FIXED);
  LALInferenceAddVariable(runState->priorArgs, "malmquist_second_loudest_snr", &malmquist_second_loudest, LALINFERENCE_REAL8_t,LALINFERENCE_PARAM_FIXED);
  LALInferenceAddVariable(runState->priorArgs, "malmquist_network_snr", &malmquist_network, LALINFERENCE_REAL8_t, LALINFERENCE_PARAM_FIXED);
  UINT4 malmquist=1;
  LALInferenceAddVariable(runState->priorArgs, "malmquist", &malmquist, LALINFERENCE_UINT4_t, LALINFERENCE_PARAM_FIXED);
  runState->prior=&LALInferenceInspiralPrior;
  fprintf(stdout,"\nUsing Malmquist Prior with limits:\n");
  fprintf(stdout,"Loudest SNR >= %lf\n",malmquist_loudest);
  fprintf(stdout,"Second Loudest SNR >= %lf\n",malmquist_second_loudest);
  fprintf(stdout,"Network SNR >= %lf\n",malmquist_network);
  
}



/***** Initialise Nested Sampling structures ****/
/* Fill in samples from the prior distribution */
/* runState->algorithmParams must contain a variable "logLikelihoods" */
/* which contains a REAL8 array of likelihood values for the live */
/* points. */
/************************************************/
void initializeNS(LALInferenceRunState *runState)
{
	char help[]="\
Nested sampling arguments:\n\
 --Nlive N\tNumber of live points to use\n\
(--Nmcmc M)\tOver-ride auto chain length determination and use this number of MCMC samples.\n\
(--maxmcmc M)\tUse at most this number of MCMC points when autodetermining the chain (5000).\n\
(--sloppyratio S)\tNumber of sub-samples of the prior for every sample from the limited prior\n\
(--Nruns R)\tNumber of parallel samples from logt to use(1)\n\
(--tolerance dZ)\tTolerance of nested sampling algorithm (0.1)\n\
(--randomseed seed)\tRandom seed of sampling distribution\n\
(--prior )\t Set the prior to use (InspiralNormalised,SkyLoc,malmquist) default: InspiralNormalised\n\n\
(--sampleprior N)\t For Testing: Draw N samples from the prior, will not perform the nested sampling integral\n\
---------------------------------------------------------------------------------------------------\n\
--- Noise Model -----------------------------------------------------------------------------------\n\
---------------------------------------------------------------------------------------------------\n\
(--psdFit)                       Run with PSD fitting\n\
(--psdNblock)                    Number of noise parameters per IFO channel (8)\n\
(--psdFlatPrior)                 Use flat prior on psd parameters (Gaussian)\n\
(--removeLines)                  Do include persistent PSD lines in fourier-domain integration\n\
(--KSlines)                      Run with the KS test line removal\n\
(--KSlinesWidth)                 Width of the lines removed by the KS test (deltaF)\n\
(--chisquaredlines)              Run with the Chi squared test line removal\n\
(--chisquaredlinesWidth)         Width of the lines removed by the Chi squared test (deltaF)\n\
(--powerlawlines)                Run with the power law line removal\n\
(--powerlawlinesWidth)           Width of the lines removed by the power law test (deltaF)\n\
(--xcorrbands)                   Run PSD fitting with correlated frequency bands\n\
\n";
//(--tdlike)\tUse time domain likelihood.\n";

	ProcessParamsTable *ppt=NULL;
	ProcessParamsTable *commandLine=runState->commandLine;
	/* Print command line arguments if help requested */
	ppt=LALInferenceGetProcParamVal(commandLine,"--help");
	if(ppt)
	{
		fprintf(stdout,"%s",help);
		return;
	}

	INT4 tmpi=0,randomseed=0;
	REAL8 tmp=0;
	

	
	/* Set up the appropriate functions for the nested sampling algorithm */
  runState->algorithm=&LALInferenceNestedSamplingAlgorithm;
  runState->evolve=&LALInferenceNestedSamplingOneStep;
  /* use the ptmcmc proposal to sample prior */
  runState->proposal=&NSWrapMCMCLALProposal;

  ppt=LALInferenceGetProcParamVal(commandLine,"--approx");
  if(ppt) {
    if(XLALCheckBurstApproximantFromString(ppt->value))
    // SALVO: giving the same basic jump proposal to all the burst signals. When we have more ad hoc functions we can differentiate here
      runState->proposal=&NSWrapMCMCSineGaussProposal;
  }
  REAL8 temp=1.0;
  LALInferenceAddVariable(runState->proposalArgs,"temperature",&temp,LALINFERENCE_REAL8_t,LALINFERENCE_PARAM_FIXED);

  /* Default likelihood is the frequency domain one */
  runState->likelihood=&LALInferenceUndecomposedFreqDomainLogLikelihood;


    /* Check whether to use the SkyLocalization prior. Otherwise uses the default LALInferenceInspiralPrior. That should probably be replaced with a swhich over the possible priors. */
    ppt=LALInferenceGetProcParamVal(commandLine,"--prior");
    if(ppt){
      if(!strcmp(ppt->value,"SkyLoc")) runState->prior = &LALInferenceInspiralSkyLocPrior;
      if(!strcmp(ppt->value,"malmquist")) initializeMalmquistPrior(runState);
    }
    else{
      runState->prior = &LALInferenceInspiralPrior;
    }
    /* For Compatibility with MCMC command line */
    if(LALInferenceGetProcParamVal(commandLine,"--malmquist-prior")) initializeMalmquistPrior(runState);
  
  /* Overwrite prior choice if Burst templates are used */
  ppt=LALInferenceGetProcParamVal(commandLine,"--approx");
  if(ppt) {
    if(!strcmp("SineGaussianF",ppt->value) || !strcmp("SineGaussian",ppt->value)|| !strcmp("Gaussian",ppt->value)|| !strcmp("GaussianF",ppt->value) || !strcmp("DampedSinusoid",ppt->value)|| !strcmp("DampedSinusoidF",ppt->value)){
    runState->prior = &LALInferenceSineGaussianPrior;
    XLALPrintInfo("Using (Sine)Gaussian(F) prior\n");
    }
  }

	/* Set up the prior for analytic tests if needed */
	if(LALInferenceGetProcParamVal(commandLine,"--correlatedGaussianLikelihood")){
		runState->prior=LALInferenceAnalyticNullPrior;
	}
    	if(LALInferenceGetProcParamVal(commandLine,"--bimodalGaussianLikelihood")){
		runState->prior=LALInferenceAnalyticNullPrior;
	}
        if(LALInferenceGetProcParamVal(commandLine,"--rosenbrockLikelihood")){
                runState->prior=LALInferenceAnalyticNullPrior;
        }    
	#ifdef HAVE_LIBLALXML
	runState->logsample=LogNSSampleAsMCMCSampleToArray;
	#else
	runState->logsample=LogNSSampleAsMCMCSampleToFile;
	#endif
	
	printf("set number of live points.\n");
	/* Number of live points */
	ppt=LALInferenceGetProcParamVal(commandLine,"--Nlive");
	if (!ppt) ppt=LALInferenceGetProcParamVal(commandLine,"--nlive");
	if(ppt)
		tmpi=atoi(ppt->value);
	else {
		fprintf(stderr,"Error, must specify number of live points\n");
		exit(1);
	}
	LALInferenceAddVariable(runState->algorithmParams,"Nlive",&tmpi, LALINFERENCE_INT4_t,LALINFERENCE_PARAM_FIXED);
	
	/* Number of points in MCMC chain */
	ppt=LALInferenceGetProcParamVal(commandLine,"--Nmcmc");
    	if(!ppt) ppt=LALInferenceGetProcParamVal(commandLine,"--nmcmc");
	if(ppt){
	  tmpi=atoi(ppt->value);
	LALInferenceAddVariable(runState->algorithmParams,"Nmcmc",&tmpi,
				LALINFERENCE_INT4_t,LALINFERENCE_PARAM_OUTPUT);
	printf("set number of MCMC points, over-riding auto-determination!\n");
	}
	if((ppt=LALInferenceGetProcParamVal(commandLine,"--sloppyfraction")))
        	tmp=atof(ppt->value);
    	else tmp=0.0;
    	LALInferenceAddVariable(runState->algorithmParams,"sloppyfraction",&tmp,
                    LALINFERENCE_REAL8_t,LALINFERENCE_PARAM_OUTPUT);

        /* Maximum number of points in MCMC chain */
        ppt=LALInferenceGetProcParamVal(commandLine,"--maxmcmc");
        if(ppt){
          tmpi=atoi(ppt->value);
          LALInferenceAddVariable(runState->algorithmParams,"maxmcmc",&tmpi,
                                LALINFERENCE_INT4_t,LALINFERENCE_PARAM_FIXED);
        }


	printf("set number of parallel runs.\n");
	/* Optionally specify number of parallel runs */
	ppt=LALInferenceGetProcParamVal(commandLine,"--Nruns");
	if(ppt) {
		tmpi=atoi(ppt->value);
		LALInferenceAddVariable(runState->algorithmParams,"Nruns",&tmpi,LALINFERENCE_INT4_t,LALINFERENCE_PARAM_FIXED);
	}
	
	printf("set tolerance.\n");
	/* Tolerance of the Nested sampling integrator */
	ppt=LALInferenceGetProcParamVal(commandLine,"--tolerance");
	if(ppt){
		tmp=strtod(ppt->value,(char **)NULL);
		LALInferenceAddVariable(runState->algorithmParams,"tolerance",&tmp, LALINFERENCE_REAL8_t,
					LALINFERENCE_PARAM_FIXED);
	}
	
	printf("set random seed.\n");
	/* Set up the random number generator */
	gsl_rng_env_setup();
	runState->GSLrandom = gsl_rng_alloc(gsl_rng_mt19937);
	
	/* (try to) get random seed from command line: */
	ppt = LALInferenceGetProcParamVal(commandLine, "--randomseed");
	if (ppt != NULL)
		randomseed = atoi(ppt->value);
	fprintf(stdout, " initialize(): random seed: %u\n", randomseed);
	LALInferenceAddVariable(runState->algorithmParams,"random_seed",&randomseed, LALINFERENCE_INT4_t,LALINFERENCE_PARAM_FIXED);
	gsl_rng_set(runState->GSLrandom, randomseed);
	
	return;
	
}

/*************** MAIN **********************/


int main(int argc, char *argv[]){
        char help[]="\
LALInferenceNest:\n\
Bayesian analysis tool using Nested Sampling algorithm\n\
for CBC and burst analysis. Uses LALInference library for back-end.\n\n\
Arguments for each section follow:\n\n";


	LALInferenceRunState *state;
	ProcessParamsTable *procParams=NULL;
  ProcessParamsTable *ppt=NULL;
	/* Read command line and parse */
	procParams=LALInferenceParseCommandLine(argc,argv);
  if(LALInferenceGetProcParamVal(procParams,"--help"))
  {
    fprintf(stdout,"%s",help);
  }
	/* initialise runstate based on command line */
	/* This includes reading in the data */
	/* And performing any injections specified */
	/* And allocating memory */
	state = initialize(procParams);
	/* Set up structures for nested sampling */
	initializeNS(state);
  
  /* Set up currentParams with variables to be used */
	/* Review task needs special priors */
	LALInferenceInitModelFunction initModelFunc=NULL;
  
	/* Set up currentParams with variables to be used */
	/* Review task needs special priors */
        ppt=LALInferenceGetProcParamVal(procParams,"--approx");
	if(LALInferenceGetProcParamVal(procParams,"--correlatedGaussianLikelihood")){
	  ppt=LALInferenceGetProcParamVal(procParams,"--approx");
          if (XLALCheckBurstApproximantFromString(ppt->value)){
            fprintf(stdout,"Using burst unimodal analytic likelihood\n");
            initModelFunc=&LALInferenceInitModelReviewBurstEvidence_unimod;
          }
          else
            initModelFunc=&LALInferenceInitModelReviewEvidence;
        }
        else if(LALInferenceGetProcParamVal(procParams,"--bimodalGaussianLikelihood")){
          ppt=LALInferenceGetProcParamVal(procParams,"--approx");
          if (XLALCheckBurstApproximantFromString(ppt->value))
            initModelFunc=&LALInferenceInitModelReviewBurstEvidence_bimod;
          else
            initModelFunc=&LALInferenceInitModelReviewEvidence_bimod;;
        }
  else if(LALInferenceGetProcParamVal(procParams,"--rosenbrockLikelihood")){
    ppt=LALInferenceGetProcParamVal(procParams,"--approx");
    if (XLALCheckBurstApproximantFromString(ppt->value)){
      fprintf(stderr,"Rosenbrock Likelihood not yet implemented for LIB. Exiting...\n");
      exit(1);
    }
    else
      initModelFunc=&LALInferenceInitModelReviewEvidence_banana;
  }
  else if(XLALCheckBurstApproximantFromString(ppt->value)){
	    fprintf(stdout,"--- Calling burst init variables \n");
	    initModelFunc=&LALInferenceInitBurstModel;
	}
	else{
		printf("Using default CBC init!\n");
		initModelFunc=&LALInferenceInitCBCModel;
	}

  state->initModel=initModelFunc;
	state->model = initModelFunc(state);
  if (state->model){
  state->currentParams = XLALMalloc(sizeof(LALInferenceVariables));
  memset(state->currentParams, 0, sizeof(LALInferenceVariables));
  LALInferenceCopyVariables(state->model->params, state->currentParams);
  state->templt = state->model->templt;
  }
  /* Choose the likelihood */
  LALInferenceInitLikelihood(state);

  /* Apply calibration errors if desired*/
  LALInferenceApplyCalibrationErrors(state,procParams);
  
  /* Exit since we printed all command line arguments */
  if(LALInferenceGetProcParamVal(state->commandLine,"--help"))
  {
    exit(0);
  }
  
	/* Call setupLivePointsArray() to populate live points structures */
	LALInferenceSetupLivePointsArray(state);

	ppt=LALInferenceGetProcParamVal(procParams,"--approx");
	if(ppt) {
    // SALVO: We may want different if else for differnt templates in the future
    if(XLALCheckBurstApproximantFromString(ppt->value)){
      fprintf(stdout,"--- Setting burst jump proposal \n");
      LALInferenceSetupSineGaussianProposal(state,state->currentParams,state->currentParams);
    }
    else 
	    LALInferenceSetupDefaultNSProposal(state,state->currentParams,state->currentParams);
  }
  else{
    fprintf(stderr,"ERROR: --approx is a required argument since LIB won't know whether to default to CBC or Burst approximant\n");
    exit(1);
  }
	/* write injection with noise evidence information from algorithm */
	LALInferencePrintInjectionSample(state);
	
	/* Call nested sampling algorithm */
	state->algorithm(state);

	/* end */
	return(0);
}

