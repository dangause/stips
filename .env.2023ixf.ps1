# Environment for 2023ixf PS1 Template Integration Testing
# This creates a fresh repository to test PS1 template functionality
#
# Usage:
#   ENV_FILE=.env.2023ixf.ps1 make bootstrap
#   ENV_FILE=.env.2023ixf.ps1 make dia-multiband ARGS="..."

# Repository for PS1 integration testing
REPO=/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_ps1_integration_repo

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

# SN 2023ixf Coordinates
# RA: 210.9106° (14h 03m 38.5s)
# Dec: 54.3118° (+54° 18' 42")
IXFI_RA=210.9106
IXFI_DEC=54.3118
