#!/usr/bin/bash
# Backup both the archive's metadata and django databases.

bkup_dir=/pg_data/backups/
date_string=`date --utc +%Y%m%d_%H%M`
metadata_file=$bkup_dir/archive_db_${date_string}.dump.gz
django_file=$bkup_dir/archive_db_django_${date_string}.dump.gz

# Backup the metadata db first
if pg_dump  -U postgres archive --no-owner --no-comments | gzip > $metadata_file ; then
    # If it succeeds, and the destination file exists, backup the django database
    if [[ -s $metadata_file ]] ; then
        if pg_dump -U postgres archive_django --no-owner --no-comments | gzip > $django_file ; then
            # Only if both succeed, run a find command to delete backups older than a week
            if [[ -s $django_file ]]; then
                find $bkup_dir -mtime +7 -type f -delete
            fi
        fi
    fi
fi
