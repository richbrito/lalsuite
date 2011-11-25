#!/bin/bash

#NORESAMP="1"
#NOCLEANUP="1"

## make sure we work in 'C' locale here to avoid awk sillyness
LC_ALL_old=$LC_ALL
export LC_ALL=C

## allow 'make test' to work from builddir != srcdir
builddir="./";
injectdir="../Injections/"
fdsdir="../FDS_isolated/"
dirsep=/

if [ "`echo $1 | sed 's%.*/%%'`" = "wine" ]; then
    builddir="./";
    injectdir="$1 ./"
    fdsdir="$1 ./"
    dirsep='\'
fi

edat="earth05-09.dat"
sdat="sun05-09.dat"

# test if LAL_DATA_PATH has been set ... needed to locate ephemeris-files
if [ -z "$LAL_DATA_PATH" ]; then
    if [ -n "$LALPULSAR_PREFIX" ]; then
	export LAL_DATA_PATH="${LALPULSAR_PREFIX}/share/lalpulsar";
    else
	echo
	echo "Need environment-variable LALPULSAR_PREFIX, or LAL_DATA_PATH to be set"
	echo "to your ephemeris-directory (e.g. /usr/local/share/lalpulsar)"
	echo "This might indicate an incomplete LAL+LALPULSAR installation"
	echo
	exit 1
    fi
fi

##---------- names of codes and input/output files
mfd_code="${injectdir}lalapps_Makefakedata_v4"
cfs_code="${fdsdir}lalapps_ComputeFStatistic_v2"
if test $# -eq 0 ; then
    gct_code="${builddir}lalapps_HierarchSearchGCT"
else
    gct_code="$@"
fi

testDir="./testHS_dir";
if [ ! -d "$testDir" ]; then
    mkdir -p "$testDir"
fi

SFTdir=$testDir
SFTfiles="$SFTdir${dirsep}*.sft"
SFTfiles_H1="$SFTdir${dirsep}H1-*.sft"
SFTfiles_L1="$SFTdir${dirsep}L1-*.sft"

## Tolerance of comparison
Tolerance=5e-2	## 5%

## ---------- fixed parameter of our test-signal -------------
Alpha=3.1
Delta=-0.5
h0=1.0
cosi=-0.3
psi=0.6
phi0=1.5
Freq=100.123456789
f1dot=-1e-9

## perfectly targeted search in sky
AlphaSearch=$Alpha
DeltaSearch=$Delta

## Produce skygrid file for the search
skygridfile="${testDir}${dirsep}tmpskygridfile.dat"
echo "$AlphaSearch $DeltaSearch" > $skygridfile

mfd_FreqBand=0.20;
mfd_fmin=100;
numFreqBands=4;	## produce 'frequency-split' SFTs used in E@H

Dterms=16
RngMedWindow=50

gct_FreqBand=0.01
gct_F1dotBand=2.0e-10
gct_dFreq=0.000002 #"2.0e-6"
gct_dF1dot=1.0e-10
gct_nCands=1000

sqrtSh=1

## --------- Generate fake data set time stamps -------------
echo "----------------------------------------------------------------------"
echo " STEP 0: Generating time-stamps and segments files "
echo "----------------------------------------------------------------------"
echo

Tsft=1800
startTime=852443819
refTime=862999869
Tsegment=90000
Nsegments=14

seggap=$(echo ${Tsegment} | awk '{printf "%.0f", $1 * 1.12345}')

tsFile_H1="${testDir}${dirsep}timestampsH1.dat"  # for makefakedata
tsFile_L1="${testDir}${dirsep}timestampsL1.dat"  # for makefakedata
segFile="${testDir}${dirsep}segments.dat"

if [ -r "$tsFile_H1" -a -r "$tsFile_L1" -a -r "$segFile" ]; then
    reuseSegFiles=true
    echo "Reusing '$tsFile_H1', '$tsFile_L1' and '$segFile'"
    echo
fi

tmpTime=$startTime
iSeg=1
while [ $iSeg -le $Nsegments ]; do
    t0=$tmpTime
    ## only write segment-file if we can re-use from previous runs
    if [ "$reuseSegFiles" != "true" ]; then
        t1=$(($t0 + $Tsegment))
        TspanHours=`echo $Tsegment | awk '{printf "%.7f", $1 / 3600.0 }'`
        ## first and last segment will be single-IFO only
        if [ $iSeg -eq 1 -o $iSeg -eq $Nsegments ]; then
            NSFT=`echo $Tsegment $Tsft |  awk '{print int(1.0 * $1 / $2 + 0.5) }'`
        else	## while all other segments are 2-IFO
            NSFT=`echo $Tsegment $Tsft |  awk '{print int(2.0 * $1 / $2 + 0.5) }'`
        fi
        echo "$t0 $t1 $TspanHours $NSFT" >> $segFile
    fi
    segs[$iSeg]=$tmpTime # save seg's beginning for later use
    echo "Segment: $iSeg of $Nsegments	GPS start time: ${segs[$iSeg]}"

    Tseg=$Tsft
    while [ $Tseg -le $Tsegment ]; do
        ## only write timestamps-file if it is not found already
        if [ "$reuseSegFiles" != "true" ]; then	            ## we skip segment 1 for H1
            if [ $iSeg -ne 1 ]; then
	        echo "${tmpTime} 0" >> $tsFile_H1
            fi
            if [ $iSeg -ne $Nsegments ]; then	            ## we skip segment N for L1
	        echo "${tmpTime} 0" >> $tsFile_L1
            fi
        fi
	tmpTime=$(($tmpTime + $Tsft))
	Tseg=$(($Tseg + $Tsft))
    done

    tmpTime=$(($tmpTime + $seggap))
    iSeg=$(($iSeg + 1))
done

echo
echo "----------------------------------------------------------------------"
echo " STEP 1: Generate Fake Signal"
echo "----------------------------------------------------------------------"
echo
if [ ! -d "$SFTdir" ]; then
    mkdir -p $SFTdir;
fi

FreqStep=`echo $mfd_FreqBand $numFreqBands |  awk '{print $1 / $2}'`
mfd_fBand=`echo $FreqStep $Tsft |  awk '{print ($1 - 1.5 / $2)}'`	## reduce by 1/2 a bin to avoid including last freq-bins

# construct common MFD cmd
mfd_CL_common="--Band=${mfd_fBand} --Freq=$Freq --f1dot=$f1dot --Alpha=$Alpha --Delta=$Delta --psi=$psi --phi0=$phi0 --h0=$h0 --cosi=$cosi --ephemYear=05-09 --generationMode=1 --refTime=$refTime --Tsft=$Tsft --randSeed=1000 --outSingleSFT"

if [ "$sqrtSh" != "0" ]; then
    mfd_CL_common="$mfd_CL_common --noiseSqrtSh=$sqrtSh";
fi

iFreq=1
while [ $iFreq -le $numFreqBands ]; do
    mfd_fi=`echo $mfd_fmin $iFreq $FreqStep | awk '{print $1 + ($2 - 1) * $3}'`

    # for H1:
    SFTname="${SFTdir}${dirsep}H1-${mfd_fi}_${FreqStep}.sft"
    if [ ! -r $SFTname ]; then
        cmdline="$mfd_code $mfd_CL_common --fmin=$mfd_fi --IFO=H1 --outSFTbname=$SFTname --timestampsFile=$tsFile_H1"
        echo "$cmdline";
        if ! eval "$cmdline &> /dev/null"; then
            echo "Error.. something failed when running '$mfd_code' ..."
            exit 1
        fi
    else
        echo "SFT '$SFTname' exists already ... reusing it"
    fi

    # for L1:
    SFTname="${SFTdir}${dirsep}L1-${mfd_fi}_${FreqStep}.sft"
    if [ ! -r $SFTname ]; then
        cmdline="$mfd_code $mfd_CL_common --fmin=$mfd_fi --IFO=L1 --outSFTbname=$SFTname --timestampsFile=$tsFile_L1";
        echo "$cmdline";
        if ! eval "$cmdline &> /dev/null"; then
            echo "Error.. something failed when running '$mfd_code' ..."
            exit 1
        fi
    else
        echo "SFT '$SFTname' exists already ... reusing it"
    fi

    iFreq=$(( $iFreq + 1 ))

done


echo
echo "----------------------------------------------------------------------"
echo "STEP 2: run CFSv2 over segments"
echo "----------------------------------------------------------------------"
echo
outfile_cfs="${testDir}${dirsep}CFS.dat";

if [ ! -r "$outfile_cfs" ]; then
    tmpfile_cfs="${testDir}${dirsep}__tmp_CFS.dat";
    cfs_CL_common=" --Alpha=$Alpha --Delta=$Delta --Freq=$Freq --f1dot=$f1dot --outputLoudest=$tmpfile_cfs --ephemYear=05-09 --refTime=$refTime --Dterms=$Dterms --RngMedWindow=$RngMedWindow --outputSingleFstats "
    if [ "$sqrtSh" = "0" ]; then
        cfs_CL_common="$cfs_CL_common --SignalOnly";
    fi

    TwoFsum=0
    TwoFsum_L1=0
    TwoFsum_H1=0

    for ((iSeg=1; iSeg <= $Nsegments; iSeg++)); do
        startGPS=${segs[$iSeg]}
        endGPS=$(($startGPS + $Tsegment))
        cfs_CL="$cfs_code $cfs_CL_common --minStartTime=$startGPS --maxEndTime=$endGPS"

        # ----- get multi-IFO + single-IFO F-stat values
        cmdline="$cfs_CL --DataFiles='$SFTfiles'"
        echo "$cmdline"
        if ! eval "$cmdline &> /dev/null"; then
	    echo "Error.. something failed when running '$cfs_code' ..."
	    exit 1
        fi

        resCFS=$(cat ${tmpfile_cfs} | awk '{if($1=="twoF") {printf "%.11g", $3}}')
        TwoFsum=$(echo $TwoFsum $resCFS | awk '{printf "%.11g", $1 + $2}')

        if [ $iSeg -eq 1 ]; then	## segment 1 has no H1 SFTs
            resCFS_L1=$(cat ${tmpfile_cfs} | awk '{if($1=="twoF0") {printf "%.11g", $3}}')
            TwoFsum_L1=$(echo $TwoFsum_L1 $resCFS_L1 | awk '{printf "%.11g", $1 + $2}')
        elif [ $iSeg -eq $Nsegments ]; then	## segment N has no L1 SFTs
            resCFS_H1=$(cat ${tmpfile_cfs} | awk '{if($1=="twoF0") {printf "%.11g", $3}}')	## therefore 'H1' is the first and only detector
            TwoFsum_H1=$(echo $TwoFsum_H1 $resCFS_H1 | awk '{printf "%.11g", $1 + $2}')
        else ## order here seems to be reversed from GCT-ordering!!
            resCFS_H1=$(cat ${tmpfile_cfs} | awk '{if($1=="twoF0") {printf "%.11g", $3}}')	## 'H1' is first
            TwoFsum_H1=$(echo $TwoFsum_H1 $resCFS_H1 | awk '{printf "%.11g", $1 + $2}')

            resCFS_L1=$(cat ${tmpfile_cfs} | awk '{if($1=="twoF1") {printf "%.11g", $3}}')	## 'L1' second
            TwoFsum_L1=$(echo $TwoFsum_L1 $resCFS_L1 | awk '{printf "%.11g", $1 + $2}')
        fi
    done

    TwoFAvg=$(echo    $TwoFsum    $Nsegments | awk '{printf "%.11g", $1 / ($2)}')
    TwoFAvg_H1=$(echo $TwoFsum_H1 $Nsegments | awk '{printf "%.11g", $1 / ($2-1)}')	## H1 has one segment less (the first one)
    TwoFAvg_L1=$(echo $TwoFsum_L1 $Nsegments | awk '{printf "%.11g", $1 / ($2-1)}')	## L1 also one segment less (the last one)
    echo "$TwoFAvg	$TwoFAvg_H1	$TwoFAvg_L1" > $outfile_cfs
else
    echo "CFS result file '$outfile_cfs' exists already ... reusing it"
    cfs_res=$(cat $outfile_cfs)
    TwoFAvg=$(echo $cfs_res | awk '{print $1}')
    TwoFAvg_H1=$(echo $cfs_res | awk '{print $2}')
    TwoFAvg_L1=$(echo $cfs_res | awk '{print $3}')
fi

echo
echo "==>   Average <2F_multi>=$TwoFAvg, <2F_H1>=$TwoFAvg_H1, <2F_L1>=$TwoFAvg_L1"

## ---------- run GCT code on this data ----------------------------------------

gct_CL_common="--gridType1=3 --nCand1=$gct_nCands --skyRegion='allsky' --Freq=$Freq --DataFiles='$SFTfiles' --skyGridFile='./$skygridfile' --printCand1 --semiCohToplist --df1dot=$gct_dF1dot --f1dot=$f1dot --f1dotBand=$gct_F1dotBand --dFreq=$gct_dFreq --FreqBand=$gct_FreqBand --refTime=$refTime --segmentList=$segFile --ephemE=$edat --ephemS=$sdat --outputFX --Dterms=$Dterms --blocksRngMed=$RngMedWindow"
if [ "$sqrtSh" = "0" ]; then
    gct_CL_common="$gct_CL_common --SignalOnly";
fi

echo
echo "----------------------------------------------------------------------------------------------------"
echo " STEP 3: run HierarchSearchGCT using Resampling (perfect match) and segment-list file"
echo "----------------------------------------------------------------------------------------------------"
echo

rm -f checkpoint.cpt # delete checkpoint to start correctly
outfile_GCT_RS="${testDir}${dirsep}GCT_RS.dat"
timingsfile_RS="${testDir}${dirsep}timing_RS.dat"

if [ -z "$NORESAMP" ]; then
    cmdline="$gct_code $gct_CL_common --useResamp=true --fnameout=$outfile_GCT_RS --outputTiming=$timingsfile_RS"
    echo "$cmdline"
    if ! eval "$cmdline &> /dev/null"; then
	echo "Error.. something failed when running '$gct_code' ..."
	exit 1
    fi
    topline=$(sort -nr -k6,6 $outfile_GCT_RS | head -1)
    resGCT_RS=$(echo $topline | awk '{print $6}')
    resGCT_RS_L1=$(echo $topline | awk '{print $8}')
    resGCT_RS_H1=$(echo $topline | awk '{print $9}')
    freqGCT_RS=$(echo $topline | awk '{print $1}')
else
    echo
    echo "Not run with resampling."
fi


echo
echo "----------------------------------------------------------------------------------------------------"
echo " STEP 4: run HierarchSearchGCT using LALDemod (perfect match) and --tStack and --nStacksMax"
echo "----------------------------------------------------------------------------------------------------"
echo

rm -f checkpoint.cpt # delete checkpoint to start correctly
outfile_GCT_DM="${testDir}${dirsep}GCT_DM.dat"
timingsfile_DM="${testDir}${dirsep}timing_DM.dat"

cmdline="$gct_code $gct_CL_common --useResamp=false --fnameout=$outfile_GCT_DM --outputTiming=$timingsfile_DM"
echo $cmdline
if ! eval "$cmdline &> /dev/null"; then
    echo "Error.. something failed when running '$gct_code' ..."
    exit 1
fi

topline=$(sort -nr -k6,6 $outfile_GCT_DM | head -1)
resGCT_DM=$(echo $topline  | awk '{print $6}')
resGCT_DM_L1=$(echo $topline  | awk '{print $8}')
resGCT_DM_H1=$(echo $topline  | awk '{print $9}')
freqGCT_DM=$(echo $topline | awk '{print $1}')

## ---------- compute relative differences and check against tolerance --------------------
awk_reldev='{printf "%.2e", sqrt(($1-$2)*($1-$2))/(0.5*($1+$2)) }'

if [ -z "$NORESAMP" ]; then
    reldev_RS=$(echo $TwoFAvg $resGCT_RS | awk "$awk_reldev")
    reldev_RS_H1=$(echo $TwoFAvg_H1 $resGCT_RS_H1 | awk "$awk_reldev")
    reldev_RS_L1=$(echo $TwoFAvg_L1 $resGCT_RS_L1 | awk "$awk_reldev")
    freqreldev_RS=$(echo $Freq $freqGCT_RS | awk "$awk_reldev")
fi

reldev_DM=$(echo $TwoFAvg $resGCT_DM | awk "$awk_reldev")
reldev_DM_H1=$(echo $TwoFAvg_H1 $resGCT_DM_H1 | awk "$awk_reldev")
reldev_DM_L1=$(echo $TwoFAvg_L1 $resGCT_DM_L1 | awk "$awk_reldev")
freqreldev_DM=$(echo $Freq $freqGCT_DM | awk "$awk_reldev")

# ---------- Check relative deviations against tolerance, report results ----------
retstatus=0
awk_isgtr='{if($1>$2) {print "1"}}'

echo
echo "--------- Timings ------------------------------------------------------------------------------------------------"
awk_timing='BEGIN { timingsum = 0; counter=0; } { timingsum=timingsum+$8; counter=counter+1; } END {printf "%.3g", timingsum/counter}'
timing_DM=$(sed '/^%.*/d' $timingsfile_DM | awk "$awk_timing")
timing_RS=$(sed '/^%.*/d' $timingsfile_RS | awk "$awk_timing")
echo " GCT-LALDemod:  tauCoh = $timing_DM s"
echo " GCT-Resamp:    tauCoh = $timing_RS s"

echo
echo "--------- Compare results ----------------------------------------------------------------------------------------"
echo "                     	<2F_multi>	<2F_H1>  	<2F_L1>  	@ Freq [Hz]     	(reldev, reldev_H1, reldev_L1, reldev_Freq)"
echo    "==>  CFSv2:         	$TwoFAvg 	$TwoFAvg_H1   	$TwoFAvg_L1   	@ $Freq 	[Tolerance = ${Tolerance}]"

echo -n "==>  GCT-LALDemod: 	$resGCT_DM 	$resGCT_DM_H1 	$resGCT_DM_L1  	@ $freqGCT_DM 	($reldev_DM, $reldev_DM_H1, $reldev_DM_L1, $freqreldev_DM)"
fail1=$(echo $freqreldev_DM $Tolerance | awk "$awk_isgtr")
fail2=$(echo $reldev_DM $Tolerance     | awk "$awk_isgtr")
fail3=$(echo $reldev_DM_H1 $Tolerance  | awk "$awk_isgtr")
fail4=$(echo $reldev_DM_L1 $Tolerance  | awk "$awk_isgtr")
if [ "$fail1" -o "$fail2" -o "$fail3" -o "$fail4" ]; then
    echo " ==> FAILED"
    retstatus=1
else
    echo " ==> OK"
fi

if [ -z "$NORESAMP" ]; then
    echo -n "==>  GCT-Resamp: 	$resGCT_RS 	$resGCT_RS_H1 	$resGCT_RS_L1  	@ $freqGCT_RS 	($reldev_RS, NA, NA, $freqreldev_RS)"
    fail1=$(echo $freqreldev_RS $Tolerance | awk "$awk_isgtr")
    fail2=$(echo $reldev_RS $Tolerance | awk "$awk_isgtr")
    ## these are currently defunct => not testing them
    fail3=$(echo $reldev_RS_H1 $Tolerance | awk "$awk_isgtr")
    fail4=$(echo $reldev_RS_L1 $Tolerance | awk "$awk_isgtr")
    if [ "$fail1" -o "$fail2" ]; then
        echo " ==> FAILED"
        retstatus=1
    else
        echo " ==> OK"
    fi
fi


echo "----------------------------------------------------------------------"

## clean up files
if [ -z "$NOCLEANUP" ]; then
    rm -rf $testDir
    echo "Cleaned up."
fi

## restore original locale, just in case someone source'd this file
export LC_ALL=$LC_ALL_old

exit $retstatus
