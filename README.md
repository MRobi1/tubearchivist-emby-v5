# TubeArchivist-Emby Integration v5.0+

A modern integration to sync metadata between TubeArchivist v5.0+ and Emby, organizing YouTube channels as TV Shows with yearly seasons.

## 🚀 Features

- **Full API Compatibility**: Updated for TubeArchivist v5.0+ API changes
- **Automatic Metadata Sync**: Syncs video titles, descriptions, publish dates, and channel information
- **Yearly Organization**: Groups videos by year as seasons within channel shows
- **Real-time Notifications**: Automatic sync triggered by TubeArchivist download completion
- **Robust Error Handling**: Comprehensive logging and error recovery
- **Docker Support**: Easy deployment with Docker Compose
- **Flexible Configuration**: Support for both config files and environment variables

## 📋 Requirements

- TubeArchivist v5.0 or later
- Emby Server (any recent version)
- Python 3.11+ (if running without Docker)
- Docker and Docker Compose (recommended)

## 🛠️ Installation

### Option 1: Docker Compose (Recommended)

1. **Clone or download the integration files**
   ```bash
   git clone https://github.com/MRobi1/tubearchivist-emby-v5
   cd tubearchivist-emby-v5
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Update docker-compose.yml**
   - Set the correct paths for your YouTube media folder
   - Configure network settings if needed

4. **Start the integration**
   ```bash
   docker-compose up -d tubearchivist-emby
   ```

### Option 2: Manual Installation

1. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure the integration**
   ```bash
   cp config.sample.json config.json
   # Edit config.json with your settings
   ```

3. **Run the integration**
   ```bash
   # One-time sync
   python main.py
   
   # Run as server for notifications
   python main.py --server
   ```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TA_URL` | TubeArchivist URL (e.g., http://tubearchivist:8000) | ✅ | - |
| `TA_TOKEN` | TubeArchivist API token | ✅ | - |
| `EMBY_URL` | Emby server URL (e.g., http://emby:8096) | ✅ | - |
| `EMBY_TOKEN` | Emby API key | ✅ | - |
| `EMBY_FOLDER` | Name of YouTube library in Emby | ❌ | YouTube |
| `LISTEN_PORT` | Port for notification server | ❌ | 8001 |
| `TA_VIDEO_PATH` | Path to YouTube media folder | ❌ | /youtube |

### Getting API Tokens

#### TubeArchivist API Token
1. Open TubeArchivist web interface
2. Go to Settings → API
3. Generate or copy your API token

#### Emby API Key
1. Open Emby web interface as admin
2. Go to Settings → Advanced → API Keys
3. Create a new API key for the integration

## 📺 Emby Setup

### 1. Mount YouTube Folder
Add your TubeArchivist `/youtube` folder to Emby:
```yaml
volumes:
  - /path/to/tubearchivist/youtube:/youtube:ro  # READ-ONLY is crucial!
```

**⚠️ IMPORTANT**: Mount as read-only (`ro`) to prevent Emby from modifying TubeArchivist files.

### 2. Create YouTube Library
1. In Emby, go to Settings → Libraries
2. Add new library with these settings:
   - **Content Type**: Shows
   - **Display Name**: YouTube (or match `EMBY_FOLDER` config)
   - **Folder**: Point to your mounted YouTube folder
   - **Metadata Downloaders**: Disable all
   - **Image Fetchers**: Disable all
   - **Automatically refresh**: Never

### 3. Enable Backdrops (Optional)
For better channel art viewing:
1. Go to Settings → Display
2. Enable "Backdrops"

## 🔄 Usage

### Manual Sync
```bash
# Docker
docker exec -it tubearchivist-emby python main.py

# Manual installation
python main.py
```

### Automatic Sync via Notifications
Configure TubeArchivist to send notifications on download completion:

1. In TubeArchivist Settings → Scheduling
2. Find "Start download" schedule
3. Add notification URL: `json://tubearchivist-emby:8001`
4. Save settings

The integration will automatically sync when downloads complete.

### Server Mode
Run as a persistent service to handle notifications:
```bash
# Docker (default in docker-compose)
docker-compose up -d tubearchivist-emby

# Manual
python main.py --server
```

## 🏗️ How It Works

### Metadata Synchronization
The integration performs these steps:

1. **Connects** to both TubeArchivist and Emby APIs
2. **Fetches** all videos from TubeArchivist
3. **Matches** videos with Emby library items by YouTube ID
4. **Updates** Emby metadata with:
   - Video title and description
   - Publish date and year
   - Channel name (as studio)
   - Tags and categories
   - YouTube ID for future reference

### Organization Structure
Videos are organized in Emby as:
```
YouTube Library/
├── Channel Name 1/
│   ├── Season 2021/
│   │   ├── video1.mp4
│   │   └── video2.mp4
│   ├── Season 2022/
│   │   ├── video3.mp4
│   │   └── video4.mp4
│   └── Season 2023/
│       └── video5.mp4
└── Channel Name 2/
    └── Season 2023/
        └── video6.mp4
```

## 🔧 Troubleshooting

### Common Issues

#### "Library not found" Error
- Ensure the Emby library name matches `EMBY_FOLDER` config
- Verify the library exists and is accessible

#### "Videos not found in Emby" Warning
- Run Emby library scan first: Settings → Libraries → Scan Library
- Check file permissions on mounted YouTube folder
- Verify YouTube folder is properly mounted in both containers

#### API Connection Failed
- Check URLs are accessible from the integration container
- Verify API tokens are correct and have required permissions
- Check firewall and network settings

#### Permission Errors
```bash
# Fix ownership of YouTube folder
sudo chown -R 1000:1000 /path/to/youtube/folder

# For Emby container access
sudo chown -R 1000:1000 /path/to/youtube/folder
```

### Debugging

#### Enable Debug Logging
```bash
# Environment variable
LOG_LEVEL=DEBUG

# Or in config.json
"log_level": "DEBUG"
```

#### Check Container Logs
```bash
docker logs -f tubearchivist-emby
```

#### Test API Connectivity
```bash
# Test TubeArchivist API
curl -H "Authorization: Token YOUR_TOKEN" http://tubearchivist:8000/api/ping/

# Test Emby API
curl http://emby:8096/System/Info?api_key=YOUR_API_KEY
```

## 🔄 Migration from v0.4.x

If migrating from the older tubearchivist-emby integration:

1. **Backup** your current Emby library metadata
2. **Stop** the old integration
3. **Deploy** this new version
4. **Run** initial sync: `docker exec -it tubearchivist-emby python main.py`
5. **Configure** TubeArchivist notifications to point to new integration

### Breaking Changes from v0.4.x
- New API endpoints for TubeArchivist v5.0+
- Updated metadata structure
- Improved error handling and logging
- Docker-first approach
- Enhanced configuration options

## 📚 API Reference

### TubeArchivist v5.0+ API Endpoints Used
- `GET /api/ping/` - Health check
- `GET /api/video/` - List videos with pagination
- `GET /api/video/{id}/` - Get video details
- `GET /api/channel/` - List channels
- `GET /api/channel/{id}/` - Get channel details

### Emby API Endpoints Used
- `GET /Library/VirtualFolders` - List libraries
- `GET /Items` - List library items
- `GET /Items/{id}` - Get item details
- `POST /Items/{id}` - Update item metadata
- `POST /Library/VirtualFolders/{id}/Refresh` - Refresh library

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Original tubearchivist-emby by xinmans
- TubeArchivist team for the excellent media server
- Emby team for their media server platform

## 💡 Support

- **Issues**: Report bugs or request features via GitHub Issues
- **Discussions**: Join the TubeArchivist Discord or Reddit community
- **Documentation**: Check the TubeArchivist official docs for general setup help

---

**⚠️ Important Notes:**
- Always mount the YouTube folder as read-only in Emby to prevent file corruption
- Test the integration with a small library first
- Keep both TubeArchivist and Emby updated for best compatibility
- Monitor logs during initial setup to catch configuration issues early
