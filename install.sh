# install.sh - Installation script
#!/bin/bash

set -e

REPO_URL="https://github.com/your-username/tubearchivist-emby-v5"
INSTALL_DIR="tubearchivist-emby"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_banner() {
    cat << 'EOF'
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     TubeArchivist-Emby Integration v5.0+                     ║
║     Updated for TubeArchivist v5.0+ compatibility            ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
}

check_dependencies() {
    log_info "Checking system dependencies..."
    
    # Check for required commands
    local required_commands=("git" "docker" "curl")
    local missing_commands=()
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_commands+=("$cmd")
        fi
    done
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_commands[*]}"
        log_info "Please install them and try again"
        exit 1
    fi
    
    # Check Docker daemon
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    log_info "All dependencies satisfied"
}

install_integration() {
    log_info "Installing TubeArchivist-Emby Integration..."
    
    # Create installation directory
    if [[ -d "$INSTALL_DIR" ]]; then
        log_warn "Directory $INSTALL_DIR already exists"
        read -p "Remove existing installation? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$INSTALL_DIR"
        else
            log_error "Installation cancelled"
            exit 1
        fi
    fi
    
    # Clone or download files
    if [[ -n "$REPO_URL" ]] && git ls-remote "$REPO_URL" &> /dev/null; then
        log_info "Cloning repository..."
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        log_info "Creating installation directory..."
        mkdir -p "$INSTALL_DIR"
        
        # Download files directly (if available)
        # This would typically download from releases or a file server
        log_warn "Manual file setup required - copy integration files to $INSTALL_DIR/"
    fi
    
    cd "$INSTALL_DIR"
    
    # Make scripts executable
    chmod +x manage.sh 2>/dev/null || true
    chmod +x install.sh 2>/dev/null || true
    
    log_info "Installation completed in $(pwd)"
}

setup_configuration() {
    log_info "Setting up initial configuration..."
    
    # Run setup through management script if available
    if [[ -f "manage.sh" ]]; then
        ./manage.sh setup
    else
        # Manual setup
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
            log_info "Created .env from example"
        fi
        
        if [[ -f "config.sample.json" ]]; then
            cp config.sample.json config.json
            log_info "Created config.json from sample"
        fi
        
        log_warn "Please edit .env and config.json with your settings"
    fi
}

show_next_steps() {
    cat << EOF

╔═══════════════════════════════════════════════════════════════╗
║                     Installation Complete!                   ║
╚═══════════════════════════════════════════════════════════════╝

Next steps:

1. Configure your settings:
   cd $INSTALL_DIR
   nano .env

2. Set up your TubeArchivist and Emby credentials:
   - TA_URL: Your TubeArchivist URL
   - TA_TOKEN: Your TubeArchivist API token
   - EMBY_URL: Your Emby server URL  
   - EMBY_TOKEN: Your Emby API key

3. Test the configuration:
   ./manage.sh health

4. Start the integration:
   ./manage.sh start

5. Run initial sync:
   ./manage.sh sync

For help: ./manage.sh help

Logs: ./manage.sh logs --follow

EOF
}

main() {
    print_banner
    echo
    
    check_dependencies
    install_integration
    setup_configuration
    
    echo
    show_next_steps
}

# Run installation
main "$@"
