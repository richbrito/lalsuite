# SWIG configuration
# Author: Karl Wette, 2011
#
# serial 1

# basic version string comparison
# can only handle numeric versions separated by periods
AC_DEFUN([LALSUITE_VERSION_COMPARE],[
  vcmp_awkprog='{n = 0; while(++n <= NF) { if($n > 99) printf "ERROR"; printf "%02u", $n; } }'
  vcmp_v1=[`echo $1 | ${SED} '/[^0-9.]/d' | ${AWK} -F . "${vcmp_awkprog}" | ${SED} '/ERROR/d'`]
  vcmp_v2=[`echo $2 | ${SED} '/[^0-9.]/d' | ${AWK} -F . "${vcmp_awkprog}" | ${SED} '/ERROR/d'`]
  AS_IF([test x${vcmp_v1} = x],[AC_MSG_ERROR([could not parse version string '$1'])])
  AS_IF([test x${vcmp_v2} = x],[AC_MSG_ERROR([could not parse version string '$2'])])
  AS_IF([test ${vcmp_v1} -lt ${vcmp_v2}],[$3])
  AS_IF([test ${vcmp_v1} -eq ${vcmp_v2}],[$4])
  AS_IF([test ${vcmp_v1} -gt ${vcmp_v2}],[$5])
])

# SWIG setup and configuration
AC_DEFUN([LALSUITE_ENABLE_SWIG],[

  # minimum required SWIG version
  SWIG_MIN_VERSION=1.3.40

  # save and clear CPPFLAGS and LIBS
  swig_CPPFLAGS=${CPPFLAGS}
  swig_LIBS=${LIBS}
  CPPFLAGS=
  LIBS=

  # check for sed and awk
  AC_PROG_SED
  AC_PROG_AWK

  # check for MKDIR_P
  m4_ifdef([AC_PROG_MKDIR_P],[],[
    MKDIR_P='$(INSTALL) -d'
    AC_SUBST(MKDIR_P)
  ])

  # command line option to enable/disable all languages
  AC_ARG_ENABLE(
    [swig],
    AC_HELP_STRING(
      [--enable-swig],
      [generate SWIG wrappings for all languages]
    ),[
      case "${enableval}" in
        yes) swig_build_all=true;;
        no)  swig_build_all=false;;
        *)   AC_MSG_ERROR([invalid value '${enableval}' for --enable-swig]);;
      esac
    ],[
      swig_build_all=
    ]
  )

  # are we are binding LAL itself, or one of the other LAL libraries?
  AS_IF([test x${PACKAGE_NAME} = xlal],[
    swig_is_lal=true
  ],[
    swig_is_lal=false
  ])

  # common SWIG interface headers (with LAL only)
  AS_IF([test ${swig_is_lal} = true],[
    SWIG_HEADERS=
    AC_SUBST(SWIG_HEADERS)
  ])

  # configure SWIG target scripting languages
  swig_build=false
  LALSUITE_SWIG_LANGUAGES

  # check if any language was configured
  AM_CONDITIONAL(SWIG_BUILD,[test ${swig_build} = true])
  AS_IF([test ${swig_build} = true],[

    # check for swig binary
    AC_PATH_PROGS(SWIG,[swig],[])
    AS_IF([test "x${SWIG}" = x],[
      AC_MSG_ERROR([could not find 'swig' in path])
    ])

    # check for swig version
    AC_MSG_CHECKING([for swig version])
    swig_regex=['s|^ *SWIG [Vv]ersion \([0-9.][0-9.]*\) *$|\1|p;d']
    swig_version=[`${SWIG} -version | ${SED} "${swig_regex}"`]
    AS_IF([test "x${swig_version}" = x],[
      AC_MSG_ERROR([could not determine swig version])
    ])
    AC_MSG_RESULT([${swig_version}])

    # check if swig version is newer than required
    LALSUITE_VERSION_COMPARE([${SWIG_MIN_VERSION}],[${swig_version}],[],[],[
      AC_MSG_ERROR([require swig version >= ${SWIG_MIN_VERSION}])
    ])

    # common SWIG language build makefile
    SWIG_COMMON_MK="${srcdir}/../lal/swig/swig-common.mk"
    AC_SUBST_FILE(SWIG_COMMON_MK)

    # SWIG makefile for generating header lists
    SWIG_HEADER_MK="${srcdir}/../lal/swig/swig-header.mk"
    AC_SUBST_FILE(SWIG_HEADER_MK)

    # symbols to define when generating SWIG wrapping code
    SWIG_SWIG_DEFINES=
    AC_SUBST(SWIG_SWIG_DEFINES)

    # symbols to define when compiling SWIG wrapping code
    SWIG_CXX_DEFINES=
    AC_SUBST(SWIG_CXX_DEFINES)

    # are we are binding LAL itself, or one of the other LAL libraries?
    AS_IF([test ${swig_is_lal} = true],[
      SWIG_SWIG_DEFINES="${SWIG_SWIG_DEFINES} SWIGLAL_IS_LAL"
    ])

    # are we (not) in debugging mode?
    AS_IF([test x${enable_debug} = xno],[
      SWIG_SWIG_DEFINES="${SWIG_SWIG_DEFINES} SWIGLAL_NDEBUG"
      SWIG_CXX_DEFINES="${SWIG_CXX_DEFINES} SWIGLAL_NDEBUG"
    ])

    # try to figure out the underlying type of int64_t
    AC_CHECK_HEADERS([stdint.h],[],[
      AC_MSG_ERROR([could not find 'stdint.h'])
    ])
    AC_MSG_CHECKING([underlying type of int64_t])
    AC_LANG_PUSH([C++])
    AC_COMPILE_IFELSE(
      [
        AC_LANG_PROGRAM([AC_INCLUDES_DEFAULT],[
          int64_t i64 = 0; const long int *pli = &i64;
        ])
      ],[
        AC_MSG_RESULT([long int])
        swig_wordsize=SWIGWORDSIZE64
      ],[
        AC_COMPILE_IFELSE(
          [
            AC_LANG_PROGRAM([AC_INCLUDES_DEFAULT],[
              int64_t i64 = 0; const long long int *plli = &i64;
            ])
          ],[
            AC_MSG_RESULT([long long int])
            swig_wordsize=
          ],[
            AC_MSG_ERROR([could not determine underlying type of int64_t])
          ]
        )
      ]
    )
    AC_LANG_POP([C++])
    SWIG_SWIG_DEFINES="${SWIG_SWIG_DEFINES} ${swig_wordsize}"

    # ensure that all LAL library modules share type information
    SWIG_SWIG_DEFINES="${SWIG_SWIG_DEFINES} SWIG_TYPE_TABLE=swiglaltypetable"

    # make SWIG use C++ casts
    SWIG_SWIG_DEFINES="${SWIG_SWIG_DEFINES} SWIG_CPLUSPLUS_CAST"

    # define C99 constant and limit macros
    SWIG_CXX_DEFINES="${SWIG_CXX_DEFINES} __STDC_CONSTANT_MACROS __STDC_LIMIT_MACROS"               

    # common SWIG interface headers (with LAL only)
    AS_IF([test ${swig_is_lal} = true],[
      SWIG_HEADERS="${SWIG_HEADERS} swiglal-common.i"
    ])

    # path SWIG should look in for header files:
    # keep any -I options in CPPFLAGS, without the -I prefix
    SWIG_INCLPATH=[`for n in ${swig_CPPFLAGS}; do echo $n | ${SED} 's|^-I||p;d'; done`]
    SWIG_INCLPATH=[`echo ${SWIG_INCLPATH}`]   # get rid of newlines
    AC_SUBST(SWIG_INCLPATH)

    # path SWIG should look in for libraries:
    # keep any -L options in _LIB variables, without the -L prefix
    # keep any "lib*.la" files, replace filename with $objdir;
    swig_regex=['s|^-L||p;s|lib[^/][^/]*\.la|'"${objdir}"'|p;d']
    SWIG_LIBPATH="${LAL_LIBS} ${LALSUPPORT_LIBS} ${swig_LIBS}"
    SWIG_LIBPATH=[`for n in ${SWIG_LIBPATH}; do echo $n | ${SED} "${swig_regex}"; done`]
    SWIG_LIBPATH=[`echo ${SWIG_LIBPATH}`]   # get rid of newlines
    # add pre-install locations for lal, lalsupport, and lal* libraries
    SWIG_LIBPATH="${SWIG_LIBPATH} \$(top_builddir)/lib/${objdir}"
    SWIG_LIBPATH="${SWIG_LIBPATH} \$(top_builddir)/packages/support/src/${objdir}"
    SWIG_LIBPATH="${SWIG_LIBPATH} \$(top_builddir)/src/${objdir}"
    AC_SUBST(SWIG_LIBPATH)

  ],[

    # if no SWIG languages were found
    SWIG_WRAPPINGS="NONE"
    SWIG_COMMON_MK="/dev/null"
    SWIG_HEADER_MK="/dev/null"

  ])

  # restore CPPFLAGS and LIBS
  CPPFLAGS=${swig_CPPFLAGS}
  LIBS=${swig_LIBS}

])

# tell the SWIG wrappings to use some feature
AC_DEFUN([LALSUITE_SWIG_USE],[
  SWIG_SWIG_DEFINES="${SWIG_SWIG_DEFINES} SWIGLAL_USE_$1"
])

# SWIG language configuration
AC_DEFUN([LALSUITE_SWIG_LANGUAGE],[

  # uppercase and lowercase language name
  m4_pushdef([uppercase],translit([$1],[a-z],[A-Z]))
  m4_pushdef([lowercase],translit([$1],[A-Z],[a-z]))

  # command line option to enable/disable $1
  AC_ARG_ENABLE(
    [swig-]lowercase,
    AC_HELP_STRING(
      [--enable-swig-]lowercase,
      [generate SWIG wrappings for $1]
    ),[
      case "${enableval}" in
        yes) swig_build_]lowercase[=true;;
        no)  swig_build_]lowercase[=false;;
        *)   AC_MSG_ERROR([invalid value '${enableval}' for --enable-swig-]]lowercase[);;
      esac
    ],[
      swig_build_]lowercase[=${swig_build_all:-false}
    ]
  )

  # check whether to configure $1
  AM_CONDITIONAL(SWIG_BUILD_[]uppercase,[test ${swig_build_]lowercase[} = true])
  AS_IF([test ${swig_build_]lowercase[} = true],[
    
    # at least one language was configured
    swig_build=true

    # set message string to indicate language will be built
    SWIG_]uppercase[_ENABLE_VAL=ENABLED

    # language-specific SWIG interface header (with LAL only)
    AS_IF([test ${swig_is_lal} = true],[
      SWIG_HEADERS="${SWIG_HEADERS} ]lowercase[/swiglal-]lowercase[.i"
    ])

    # configure $1
    $2
    # $1 has been configured

  ],[
    SWIG_]uppercase[_ENABLE_VAL=DISABLED
  ])

  # clear M4 definitions
  m4_popdef([uppercase])
  m4_popdef([lowercase])

])

# SWIG languages
AC_DEFUN([LALSUITE_SWIG_LANGUAGES],[
])
