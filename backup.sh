#!/bin/bash

# Configuration
PROJECT_ROOT=$(pwd)
TIMESTAMP=$(date +"%Y%m%d:%H%M")
BACKUP_DIR="release/$TIMESTAMP"

echo "Starting backup to $BACKUP_DIR..."

# Create release directory if it doesn't exist
mkdir -p release

# Create the specific backup directory
mkdir -p "$BACKUP_DIR"

# Copy files using rsync for efficiency and easy exclusion
# Exclude: .git, venv, __pycache__, logs, release (to avoid recursive backups), DS_Store
rsync -av --progress "$PROJECT_ROOT/" "$BACKUP_DIR/" \
    --exclude '.git' \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude 'logs' \
    --exclude 'release' \
    --exclude '.DS_Store' \
    --exclude '*.log' \
    --exclude '.env'

echo "Backup completed successfully at $BACKUP_DIR"
