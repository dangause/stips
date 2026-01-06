# Environment for 2020wnt PS1 Template Integration Testing
# This creates a fresh repository to test PS1 template functionality
#
# Usage:
#   ENV_FILE=.env.2020wnt.ps1 make bootstrap
#   ENV_FILE=.env.2020wnt.ps1 ./test_ps1_integration.sh --dry-run

# Repository for PS1 integration testing
REPO=/Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_ps1_integration_repo

# Stack and package paths (same as main .env)
STACK_DIR=/Users/dangause/Developer/lick/lsst/lsst_stack
OBS_NICKEL=/Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
RAW_PARENT_DIR=/Users/dangause/Developer/lick/data
REFCAT_REPO=/Users/dangause/Developer/lick/lsst/lsst_stack/stack/refcats
CP_PIPE_DIR=${STACK_DIR}/cp_pipe

# Lick Archive Configuration
LICK_ARCHIVE_DIR=/Users/dangause/Developer/lick/lick_searchable_archive
LICK_ARCHIVE_URL=https://archive.ucolick.org/archive
LICK_ARCHIVE_INSTR=NICKEL_DIR

# SN 2020wnt Coordinates
# RA: 56.66° (3h 46m 38.4s)
# Dec: 43.23° (+43° 13' 48")
IXFI_RA=56.66
IXFI_DEC=43.23
