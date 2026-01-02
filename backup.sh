#!/bin/bash

################################################################################
# Calendar Sync System - Automated Backup Script
# Backs up PostgreSQL database and Baikal data
# Author: Claude (for Sean)
# Version: 1.0.0
################################################################################

set -euo pipefail  # Exit on error, undefined variables, and pipe failures

# Configuration
BACKUP_DIR="${BACKUP_PATH:-/opt/calendar-sync/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
POSTGRES_USER="${POSTGRES_USER:-calendaruser}"
POSTGRES_DB="${POSTGRES_DB:-calendardb}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

################################################################################
# Main Backup Function
################################################################################

main() {
    log_info "Starting backup process..."
    
    # Create backup directory if it doesn't exist
    mkdir -p "$BACKUP_DIR"
    
    # Create timestamped backup subdirectory
    BACKUP_SUBDIR="$BACKUP_DIR/backup_$TIMESTAMP"
    mkdir -p "$BACKUP_SUBDIR"
    
    log_info "Backup location: $BACKUP_SUBDIR"
    
    # Backup PostgreSQL database
    backup_postgres
    
    # Backup Baikal data
    backup_baikal
    
    # Compress backup
    compress_backup
    
    # Clean old backups
    cleanup_old_backups
    
    log_info "Backup completed successfully!"
    log_info "Backup file: ${BACKUP_SUBDIR}.tar.gz"
}

################################################################################
# Backup PostgreSQL Database
################################################################################

backup_postgres() {
    log_info "Backing up PostgreSQL database..."
    
    local db_backup_file="$BACKUP_SUBDIR/postgres_${POSTGRES_DB}.sql"
    
    # Use docker-compose exec to run pg_dump
    if command -v docker-compose &> /dev/null; then
        docker-compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$db_backup_file"
    else
        log_error "docker-compose not found. Cannot backup database."
        return 1
    fi
    
    if [ -f "$db_backup_file" ]; then
        local size=$(du -h "$db_backup_file" | cut -f1)
        log_info "Database backup completed: $db_backup_file ($size)"
    else
        log_error "Database backup failed!"
        return 1
    fi
}

################################################################################
# Backup Baikal Data
################################################################################

backup_baikal() {
    log_info "Backing up Baikal data..."
    
    local baikal_backup_dir="$BACKUP_SUBDIR/baikal"
    
    # Copy Baikal config and data directories
    if [ -d "baikal/config" ] && [ -d "baikal/data" ]; then
        mkdir -p "$baikal_backup_dir"
        cp -r baikal/config "$baikal_backup_dir/"
        cp -r baikal/data "$baikal_backup_dir/"
        
        local size=$(du -sh "$baikal_backup_dir" | cut -f1)
        log_info "Baikal backup completed: $baikal_backup_dir ($size)"
    else
        log_warn "Baikal directories not found. Skipping Baikal backup."
    fi
}

################################################################################
# Compress Backup
################################################################################

compress_backup() {
    log_info "Compressing backup..."
    
    tar -czf "${BACKUP_SUBDIR}.tar.gz" -C "$BACKUP_DIR" "backup_$TIMESTAMP"
    
    if [ -f "${BACKUP_SUBDIR}.tar.gz" ]; then
        local size=$(du -h "${BACKUP_SUBDIR}.tar.gz" | cut -f1)
        log_info "Backup compressed: ${BACKUP_SUBDIR}.tar.gz ($size)"
        
        # Remove uncompressed backup directory
        rm -rf "$BACKUP_SUBDIR"
        log_info "Removed uncompressed backup directory"
    else
        log_error "Compression failed!"
        return 1
    fi
}

################################################################################
# Clean Old Backups
################################################################################

cleanup_old_backups() {
    log_info "Cleaning up backups older than $RETENTION_DAYS days..."
    
    # Find and delete old backup files
    local deleted_count=0
    while IFS= read -r old_backup; do
        rm -f "$old_backup"
        deleted_count=$((deleted_count + 1))
        log_info "Deleted old backup: $(basename "$old_backup")"
    done < <(find "$BACKUP_DIR" -name "backup_*.tar.gz" -type f -mtime +"$RETENTION_DAYS")
    
    if [ $deleted_count -gt 0 ]; then
        log_info "Deleted $deleted_count old backup(s)"
    else
        log_info "No old backups to delete"
    fi
}

################################################################################
# Error Handler
################################################################################

error_handler() {
    log_error "Backup failed with error on line $1"
    exit 1
}

trap 'error_handler $LINENO' ERR

################################################################################
# Entry Point
################################################################################

# Change to script directory
cd "$(dirname "$0")"

# Run main function
main "$@"
