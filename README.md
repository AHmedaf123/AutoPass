# AutoPass - AI-Powered LinkedIn Job Auto-Applier

An intelligent job application automation system that uses AI to automatically apply to LinkedIn jobs with "Easy Apply" functionality. Features real-time monitoring, session management, and smart form filling.

## Prerequisites

- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- Docker (optional, for containerized deployment)

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd autopass
```

### 2. Environment Configuration

Copy and configure environment variables:

```bash
cp .env.example .env  # If available, or create .env with:
```

Required environment variables:
```env
ENVIRONMENT=development
DEBUG=True

# Database
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/jobapplier

# Redis
REDIS_URL=redis://localhost:6379/0

# LinkedIn Credentials
Email=your-linkedin-email@example.com
Password=your-linkedin-password

# Encryption Keys (generate secure keys)
FERNET_KEY=<32-byte-base64-fernet-key>
BASELINE_COOKIES_MASTER_KEY=<32-byte-base64-aes-key>

# JWT
JWT_SECRET_KEY=<secure-jwt-secret>

# AI (Optional)
OPENROUTER_API_KEY=<your-openrouter-api-key>
```

### 3. Database Setup

Create PostgreSQL database and run migrations:

```bash
# Create database
python scripts/create_db.py

# Run migrations (if using Alembic)
alembic upgrade head

# Or run manual migrations
python run_migration.py
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 5. Verify System

```bash
python scripts/verify_system.py
```

### 6. Run Application

```bash
# Development
uvicorn main:socket_app --reload --host 0.0.0.0 --port 8000

# Production
gunicorn main:socket_app --worker-class uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:8000
```

## Docker Deployment

```bash
# Build and run
docker build -t autopass .
docker run -p 8000:8000 --env-file .env autopass
```

## API Endpoints

- `GET /health` - Health check
- WebSocket: `/socket.io` - Real-time updates

## Key Features

- 🤖 AI-powered job matching and form filling
- 🔄 Real-time application status via Socket.IO
- 🗄️ Async PostgreSQL with connection pooling
- ⚡ Redis caching and Celery task queue
- 🛡️ Session management with health checks
- 📊 Rate limiting and cooldown management
- 🔐 Secure credential encryption
- 📱 Firebase push notifications (optional)

## Architecture

- **Backend**: FastAPI with async SQLAlchemy
- **Database**: PostgreSQL with Alembic migrations
- **Cache/Queue**: Redis
- **Automation**: Playwright + Selenium
- **AI**: OpenRouter API (GPT models)
- **Real-time**: Socket.IO

## Security Notes

- Store credentials securely in environment variables
- Use strong encryption keys for production
- Enable rate limiting to prevent abuse
- Monitor session health and handle LinkedIn restrictions

## Troubleshooting

- Ensure PostgreSQL and Redis are running
- Check environment variables are loaded correctly
- Verify Playwright browsers are installed
- Check logs for Socket.IO connection issues</content>
<parameter name="filePath">E:\JOB\Auto-Applier\AutoPASS\README.md