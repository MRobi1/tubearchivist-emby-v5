#!/bin/bash
# manage.sh - Management script for TubeArchivist-Emby Integration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_NAME="tubearchivist-emby"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

show_usage() {
    cat << EOF
TubeArchivist-Emby Integration Management Script

Usage: $0 COMMAND [OPTIONS]

Commands:
    setup           Initial setup and configuration
    start           Start the integration service
    stop            Stop the integration service
    restart         Restart the integration service
    status          Show service status
    logs            Show service logs
    sync            Run one-time sync
    health          Perform health check
    stats           Show synchronization statistics
    clean           Clean orphaned metadata
    test            Test notification endpoint
    update          Update the integration
    backup          Backup configuration and data
    restore FILE    Restore from backup

Options:
    -f, --follow    Follow logs (for logs command)
    -h, --help      Show this help message

Examples:
    $0 setup                    # Initial setup
    $0 start                    # Start service
    $0 logs --follow           # Follow logs
    $0 sync                    # Manual sync
    $0 health                  # Health check

EOF
}

check_requirements() {
    log_info "Checking requirements..."
    
    # Check if Docker is installed and running
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    # Check if Docker Compose is available
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    log_info "Requirements check passed"
}

setup_config() {
    log_info "Setting up configuration..."
    
    # Create config directory if it doesn't exist
    mkdir -p "$SCRIPT_DIR/config"
    
    # Copy sample config if config doesn't exist
    if [[ ! -f "$SCRIPT_DIR/config.json" && -f "$SCRIPT_DIR/config.sample.json" ]]; then
        cp "$SCRIPT_DIR/config.sample.json" "$SCRIPT_DIR/config.json"
        log_info "Created config.json from sample"
    fi
    
    # Copy sample env if .env doesn't exist
    if [[ ! -f "$SCRIPT_DIR/.env" && -f "$SCRIPT_DIR/.env.example" ]]; then
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        log_info "Created .env from example"
        log_warn "Please edit .env file with your configuration"
    fi
    
    # Check if critical config values are set
    if [[ -f "$SCRIPT_DIR/.env" ]]; then
        source "$SCRIPT_DIR/.env"
        
        if [[ -z "$TA_URL" || -z "$TA_TOKEN" || -z "$EMBY_URL" || -z "$EMBY_TOKEN" ]]; then
            log_warn "Please configure required variables in .env file:"
            log_warn "  TA_URL, TA_TOKEN, EMBY_URL, EMBY_TOKEN"
        fi
    fi
    
    log_info "Configuration setup complete"
}

start_service() {
    log_info "Starting TubeArchivist-Emby integration..."
    
    if docker-compose ps | grep -q "$CONTAINER_NAME"; then
        log_warn "Service appears to already be running"
        return
    fi
    
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d $CONTAINER_NAME
    else
        docker compose up -d $CONTAINER_NAME
    fi
    
    log_info "Service started successfully"
    
    # Wait a moment and check if it's running
    sleep 3
    if docker ps | grep -q "$CONTAINER_NAME"; then
        log_info "Container is running"
    else
        log_error "Container failed to start, check logs with: $0 logs"
        exit 1
    fi
}

stop_service() {
    log_info "Stopping TubeArchivist-Emby integration..."
    
    if command -v docker-compose &> /dev/null; then
        docker-compose stop $CONTAINER_NAME
    else
        docker compose stop $CONTAINER_NAME
    fi
    
    log_info "Service stopped"
}

restart_service() {
    log_info "Restarting TubeArchivist-Emby integration..."
    stop_service
    sleep 2
    start_service
}

show_status() {
    log_info "Service Status:"
    echo
    
    # Check if container exists and is running
    if docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep "$CONTAINER_NAME"; then
        echo
        log_info "Container is running"
        
        # Show resource usage
        echo
        log_info "Resource Usage:"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" "$CONTAINER_NAME" 2>/dev/null || true
        
    elif docker ps -a --format "table {{.Names}}\t{{.Status}}" | grep "$CONTAINER_NAME"; then
        echo
        log_warn "Container exists but is not running"
    else
        log_warn "Container does not exist"
    fi
    
    # Show recent logs
    echo
    log_info "Recent logs:"
    docker logs --tail 10 "$CONTAINER_NAME" 2>/dev/null || log_warn "No logs available"
}

show_logs() {
    local follow_flag=""
    
    if [[ "$1" == "--follow" || "$1" == "-f" ]]; then
        follow_flag="-f"
        log_info "Following logs (Ctrl+C to exit)..."
    else
        log_info "Showing recent logs..."
    fi
    
    docker logs $follow_flag --tail 100 "$CONTAINER_NAME" 2>/dev/null || {
        log_error "Failed to get logs. Container may not be running."
        exit 1
    }
}

run_sync() {
    log_info "Running one-time synchronization..."
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        docker exec "$CONTAINER_NAME" python main.py
    else
        log_error "Container is not running. Start it first with: $0 start"
        exit 1
    fi
}

run_health_check() {
    log_info "Running health check..."
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        docker exec "$CONTAINER_NAME" python utils.py health
    else
        log_error "Container is not running. Start it first with: $0 start"
        exit 1
    fi
}

show_stats() {
    log_info "Showing synchronization statistics..."
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        docker exec "$CONTAINER_NAME" python utils.py stats
    else
        log_error "Container is not running. Start it first with: $0 start"
        exit 1
    fi
}

clean_metadata() {
    log_info "Cleaning orphaned metadata..."
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        docker exec -it "$CONTAINER_NAME" python utils.py clean
    else
        log_error "Container is not running. Start it first with: $0 start"
        exit 1
    fi
}

test_notification() {
    log_info "Testing notification endpoint..."
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        docker exec "$CONTAINER_NAME" python utils.py test-notification
    else
        log_error "Container is not running. Start it first with: $0 start"
        exit 1
    fi
}

update_service() {
    log_info "Updating TubeArchivist-Emby integration..."
    
    # Pull latest images
    if command -v docker-compose &> /dev/null; then
        docker-compose pull
    else
        docker compose pull
    fi
    
    # Rebuild if needed
    if [[ -f "$SCRIPT_DIR/Dockerfile" ]]; then
        log_info "Rebuilding container..."
        if command -v docker-compose &> /dev/null; then
            docker-compose build --no-cache $CONTAINER_NAME
        else
            docker compose build --no-cache $CONTAINER_NAME
        fi
    fi
    
    # Restart service
    restart_service
    
    log_info "Update completed"
}

backup_data() {
    local backup_dir="$SCRIPT_DIR/backups"
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local backup_file="$backup_dir/tubearchivist_emby_backup_$timestamp.tar.gz"
    
    log_info "Creating backup..."
    
    mkdir -p "$backup_dir"
    
    # Files to backup
    local files_to_backup=(
        "config.json"
        ".env"
        "docker-compose.yml"
        "sync_metrics.json"
    )
    
    # Create temporary directory for backup
    local temp_dir="/tmp/tubearchivist_emby_backup_$timestamp"
    mkdir -p "$temp_dir"
    
    # Copy files to backup
    for file in "${files_to_backup[@]}"; do
        if [[ -f "$SCRIPT_DIR/$file" ]]; then
            cp "$SCRIPT_DIR/$file" "$temp_dir/"
            log_debug "Added $file to backup"
        fi
    done
    
    # Copy config directory if it exists
    if [[ -d "$SCRIPT_DIR/config" ]]; then
        cp -r "$SCRIPT_DIR/config" "$temp_dir/"
        log_debug "Added config directory to backup"
    fi
    
    # Create tar archive
    tar -czf "$backup_file" -C "/tmp" "tubearchivist_emby_backup_$timestamp"
    
    # Cleanup temp directory
    rm -rf "$temp_dir"
    
    log_info "Backup created: $backup_file"
    
    # Keep only last 10 backups
    local old_backups=($(ls -1t "$backup_dir"/tubearchivist_emby_backup_*.tar.gz 2>/dev/null | tail -n +11))
    if [[ ${#old_backups[@]} -gt 0 ]]; then
        log_info "Removing old backups..."
        rm -f "${old_backups[@]}"
    fi
}

restore_data() {
    local backup_file="$1"
    
    if [[ -z "$backup_file" ]]; then
        log_error "Please specify backup file to restore"
        echo "Available backups:"
        ls -la "$SCRIPT_DIR/backups/"*.tar.gz 2>/dev/null || echo "No backups found"
        exit 1
    fi
    
    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        exit 1
    fi
    
    log_warn "This will overwrite existing configuration files"
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Restore cancelled"
        exit 0
    fi
    
    log_info "Restoring from backup: $backup_file"
    
    # Stop service if running
    if docker ps | grep -q "$CONTAINER_NAME"; then
        stop_service
    fi
    
    # Extract backup
    local temp_dir="/tmp/tubearchivist_emby_restore_$(date +%s)"
    mkdir -p "$temp_dir"
    tar -xzf "$backup_file" -C "$temp_dir"
    
    # Find the extracted directory
    local extracted_dir=$(find "$temp_dir" -name "tubearchivist_emby_backup_*" -type d | head -1)
    
    if [[ -z "$extracted_dir" ]]; then
        log_error "Could not find extracted backup directory"
        rm -rf "$temp_dir"
        exit 1
    fi
    
    # Restore files
    for file in "$extracted_dir"/*; do
        if [[ -f "$file" ]]; then
            local filename=$(basename "$file")
            cp "$file" "$SCRIPT_DIR/"
            log_debug "Restored $filename"
        fi
    done
    
    # Restore config directory if it exists
    if [[ -d "$extracted_dir/config" ]]; then
        cp -r "$extracted_dir/config" "$SCRIPT_DIR/"
        log_debug "Restored config directory"
    fi
    
    # Cleanup
    rm -rf "$temp_dir"
    
    log_info "Restore completed successfully"
    log_info "You may need to restart the service: $0 restart"
}

# Main script logic
case "${1:-help}" in
    "setup")
        check_requirements
        setup_config
        ;;
    "start")
        check_requirements
        start_service
        ;;
    "stop")
        stop_service
        ;;
    "restart")
        check_requirements
        restart_service
        ;;
    "status")
        show_status
        ;;
    "logs")
        show_logs "$2"
        ;;
    "sync")
        run_sync
        ;;
    "health")
        run_health_check
        ;;
    "stats")
        show_stats
        ;;
    "clean")
        clean_metadata
        ;;
    "test")
        test_notification
        ;;
    "update")
        check_requirements
        update_service
        ;;
    "backup")
        backup_data
        ;;
    "restore")
        restore_data "$2"
        ;;
    "help"|"-h"|"--help"|*)
        show_usage
        ;;
esac
