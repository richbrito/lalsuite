#
# Copyright (C) 2013  Branson Stephens and Chris Pankow
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


#
# =============================================================================
#
#                                   Preamble
#
# =============================================================================
#

import pygtk
pygtk.require("2.0")
import pygst
pygst.require("0.10")
import gobject
import gst

from gstlal import simplehandler
from gstlal import pipeparts
from optparse import OptionParser, Option
import os
import logging
import math
import datetime
import time
import pytz
import calendar
import json

#
# =============================================================================
#
#                                    Utils
#
# =============================================================================
#

# FIXME: Surely there is some kind of standard tool for this purpose?
# Borrowed from gracedb.
gpsEpoch = calendar.timegm((1980, 1, 6, 0,  0,  0,  0,  0,  0))

leapSeconds = map(calendar.timegm, [
    (1981, 7, 0, 0, 0, 0, 0, 0, 0),
    (1982, 7, 0, 0, 0, 0, 0, 0, 0),
    (1983, 7, 0, 0, 0, 0, 0, 0, 0),
    (1985, 7, 0, 0, 0, 0, 0, 0, 0),
    (1988, 1, 0, 0, 0, 0, 0, 0, 0),
    (1990, 1, 0, 0, 0, 0, 0, 0, 0),
    (1991, 1, 0, 0, 0, 0, 0, 0, 0),
    (1992, 7, 0, 0, 0, 0, 0, 0, 0),
    (1993, 7, 0, 0, 0, 0, 0, 0, 0),
    (1994, 7, 0, 0, 0, 0, 0, 0, 0),
    (1996, 1, 0, 0, 0, 0, 0, 0, 0),
    (1997, 7, 0, 0, 0, 0, 0, 0, 0),
    (1999, 1, 0, 0, 0, 0, 0, 0, 0),
    (2006, 1, 0, 0, 0, 0, 0, 0, 0),
    (2009, 1, 0, 0, 0, 0, 0, 0, 0),
    (2012, 7, 0, 0, 0, 0, 0, 0, 0),
])

def posixToGpsTime(posixTime):
    change = 0
    for leap in leapSeconds:
        if posixTime > leap:
            change += 1
    return posixTime + change - gpsEpoch

#
# =============================================================================
#
#                                   Options
#
# =============================================================================
#

parser = OptionParser(description = __doc__)

parser.add_option("--output-type", metavar = "name", help = "Method of output. Valid choices are 'fake' (default) and 'files'.", default = "fake")
parser.add_option("-v", "--verbose", action = "store_true", help = "Be verbose (optional).")
parser.add_option("--log-file", metavar = "name", default = "/tmp/gst_idq_receiver.log", help = "Full path to log for received frames.")

# Options for file output
parser.add_option("--frame-type", metavar = "name", help = "Specify the non-instrumental part of the frame type. The full frame type will be constructed by prepending the instrument.")
parser.add_option("--instrument", metavar = "name", help = "Specify the instrumental part of the frame type.")
parser.add_option("--output-path", metavar = "name", help = "Path to output frame files.")

# Options for multicast input.
parser.add_option("--multicast-port", metavar = "s", default = 7100, type = "int", help = "Port for receiving frames via gds_framexmitsrc")
parser.add_option("--multicast-group", metavar = "name", default="224.3.2.1", help="The multicast group from which to receive frames.")
parser.add_option("--multicast-iface", metavar = "name", default="eth2", help="Interface for listening to multicasted frames.") 

options, filenames = parser.parse_args()

#
# =============================================================================
#
#                            Some simple checks
#
# =============================================================================
#

if options.output_type=="files":
    if not options.frame_type:
        exit("Frame type argument is required for output to files.")
    if not options.instrument:
        exit("Instrument is required for output to files.")

#
# =============================================================================
#
#                            Logger & Pad Probes
#
# =============================================================================
#

logger = logging.getLogger('gst_idq_listener')
logger.setLevel(logging.INFO)

fh = logging.FileHandler(options.log_file)
logger.addHandler(fh)
fh.setFormatter(logging.Formatter('%(message)s'))

def probeEventHandler(pad,gst_buffer):
    # Load the output values into a dictionary.
    outDict = {}
    outDict['time'] = datetime.datetime.now().isoformat()
    outDict['type'] = 'event'
    outDict['name'] = gst_buffer.type.value_name

    # Serialize output as json string and log it.
    logger.info(json.dumps(outDict))

    return True
    
def probeBufferHandler(pad,gst_buffer):
    gpsstart = gst_buffer.timestamp / gst.SECOND
    end_time = gst_buffer.timestamp + gst_buffer.duration
    end_time = float(end_time)/float(gst.SECOND)
    end_time = math.ceil(end_time)
    duration = end_time - gpsstart
    is_gap   = gst_buffer.flag_is_set(gst.BUFFER_FLAG_GAP)

    # Calculate the latency with respect to the end time.
    dt_now    = datetime.datetime.now()
    posix_now = time.mktime(dt_now.timetuple())
    gps_now   = posixToGpsTime(posix_now)
    latency   = gps_now - end_time

    # Load the output values into a dictionary.
    outDict = {}
    outDict['time']     = dt_now.isoformat()
    outDict['type']     = 'buffer'
    outDict['is_gap']   = is_gap
    outDict['gpsstart'] = gpsstart
    outDict['duration'] = duration
    outDict['latency']  = latency

    # Serialize output as json string and log it.
    logger.info(json.dumps(outDict))
    return True

#
# =============================================================================
#
#                                    Main
#
# =============================================================================
#

# Set the pipeline up
pipeline = gst.Pipeline("gst_idq_listener")
mainloop = gobject.MainLoop()
handler = simplehandler.Handler(mainloop,pipeline)

# Create the framexmitsrc
src = pipeparts.mkframexmitsrc(pipeline, multicast_group=options.multicast_group,
    multicast_iface=options.multicast_iface, port=options.multicast_port)
if options.verbose:
    gst.debug_set_threshold_for_name('gds_framexmitsrc', gst.LEVEL_LOG)

# Final destination.
if options.output_type == "fake":
    fakesink = pipeparts.mkfakesink(pipeline, src)    
    fs_pad = fakesink.get_pad("sink")
    fs_pad.add_event_probe(probeEventHandler)
    fs_pad.add_buffer_probe(probeBufferHandler) 
elif options.output_type == "files":
    try:
        os.makedirs(options.output_path)
    except Exception as e:
        print "Failed with %s" % e

    # Inject tags.  The framecpp_filesink element uses the tags to figure
    # out the output filename.
    src = pipeparts.mktaginject(pipeline, src, "instrument=%s" % options.instrument)

    path = options.output_path
    if path:
        fs = pipeparts.mkframecppfilesink(pipeline, src, 
            frame_type = options.frame_type, path = options.output_path)
    else:
        fs = pipeparts.mkframecppfilesink(pipeline, src, 
            frame_type = options.frame_type)

else:
    raise ValueError("Invalid output type.")

#
# Start the thing going.
#

pipeline.set_state(gst.STATE_PLAYING)
mainloop.run()


#
# done
#
