#
# Copyright (C) 2006  Kipp Cannon
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

from optparse import OptionParser
import math
import matplotlib
matplotlib.use("Agg")
from matplotlib import figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy

import lal

from lalburst import git_version

__author__ = "Kipp Cannon <kipp.cannon@ligo.org>"
__version__ = "git id %s" % git_version.id
__date__ = git_version.date


#
# =============================================================================
#
#                                 Command Line
#
# =============================================================================
#

def parse_command_line():
	parser = OptionParser(
		version = "Name: %%prog\n%s" % git_version.verbose_msg
	)
	parser.add_option("--declination", metavar = "radians", help = "set source declination")
	parser.add_option("--instrument", metavar = "name", action = "append", default = [], help = "plot response for this instrument")
	parser.add_option("--right-ascension", metavar = "radians", help = "set source right ascension")
	parser.add_option("--show-instruments", action = "store_true", help = "list known instruments")
	parser.add_option("-v", "--verbose", action = "store_true", help = "be verbose")
	options, filenames = parser.parse_args()

	if options.show_instruments:
		print lal.cached_detector_by_prefix.keys()
	if "all" in options.instrument:
		options.instrument = lal.cached_detector_by_prefix.keys()

	try:
		options.right_ascension = float(options.right_ascension)
		options.declination = float(options.declination)
	except:
		raise ValueError, "right ascension and/or declination missing or invalid"

	return options, (filenames or [None])


#
# =============================================================================
#
#                                     Plot
#
# =============================================================================
#

def makeplot(options):
	fig = figure.Figure()
	FigureCanvasAgg(fig)
	fig.set_size_inches(6.5, 6.5 / ((1 + math.sqrt(5)) / 2))
	axes = fig.gca()
	axes.grid(True)

	xvals = numpy.arange(0.0, 401.0, 1.0, "Float64") * math.pi / 200.0
	for instrument in options.instrument:
		yvals = [plus**2.0 + cross**2.0 for (plus, cross) in map(lambda t: lal.ComputeDetAMResponse(lal.cached_detector_by_prefix[instrument].response, options.right_ascension, options.declination, 0.0, t), xvals)]
		axes.plot(xvals, yvals)

	axes.set_xlim([0.0, 2.0 * math.pi])

	axes.set_xticks(numpy.arange(9) * math.pi / 4)
	axes.set_xticklabels([r"0", r"$\pi/4$", r"$\pi/2$", r"$3\pi/4$", r"$\pi$", r"$5\pi/4$", r"$3\pi/2$", r"$7\pi/4$", r"$2\pi$"])

	axes.legend([r"\verb|%s|" % ins for ins in options.instrument])

	axes.set_xlabel("Greenwich Mean Sidereal Time (rad)")
	axes.set_ylabel(r"$F_{+}^{2} + F_{\times}^{2}$")
	axes.set_title(r"Detector Response by Sidereal Time for Source at R.A.\ %g rad, Dec.\ %g rad" % (options.right_ascension, options.declination))

	return fig


#
# =============================================================================
#
#                                    Output
#
# =============================================================================
#

options, filenames = parse_command_line()
makeplot(options).savefig(filenames[0])
