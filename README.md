# LHAS - Longitudinal Hypothesis and Analysis System

A production-grade research mission dashboard platform built with React, FastAPI, PostgreSQL, and Grobid. Optimized for Docker deployment with complete service orchestration.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation & Deployment](#installation--deployment)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Troubleshooting](#troubleshooting)
- [Production Deployment](#production-deployment)
- [Contributing](#contributing)

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Clone and enter directory
git clone <repo-url> lhas
cd lhas

# Start all services
docker compose up --build

# Access services:
# - Frontend:  http://localhost:3000
# - Backend:   http://localhost:8000
# - API Docs:  http://localhost:8000/docs
# - Grobid:    http://localhost:8070
# - Database:  localhost:5432
```

### Option 2: Local Development (Separate Services)

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
# Runs on http://localhost:8000
```

**Frontend (in another terminal):**
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

## 🏗️ Architecture

### Service Topology

```
┌─────────────────────────────────────────────────────────────┐
│                   Docker Network (Bridge)                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────┐        ┌──────────┐      ┌─────────────┐  │
│  │  Frontend  │────────│ Backend  │─────→│ PostgreSQL  │  │
│  │  Node:3000 │        │ :8000    │      │    :5432    │  │
│  └────────────┘        └──────────┘      └─────────────┘  │
│                             │                              │
│                             └─────┬─────────────────┐     │
│                                   │                 │     │
│                             ┌──────▼───┐      ┌─────▼──┐  │
│                             │  Grobid  │      │ Volumes│  │
│                             │  :8070   │      │ Storage│  │
│                             └──────────┘      └────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Frontend | React 19 + TypeScript | 19+ | Mission control UI |
| Frontend Build | Vite | 8+ | Fast build tool |
| Frontend Styling | Tailwind CSS | 3+ | Utility-first CSS |
| Backend | FastAPI | 0.104+ | REST API framework |
| Backend ORM | SQLAlchemy | 2.0+ | Database ORM (async) |
| Database Driver | asyncpg | 0.29+ | Async PostgreSQL driver |
| Database | PostgreSQL | 16 | Relational database |
| Document Parser | Grobid | 0.8.0 | PDF extraction & parsing |
| Container | Docker | Latest | Containerization |
| Orchestration | Docker Compose | 3.8 | Multi-container coordination |

## 📁 Project Structure

```
lhas/
├── frontend/                          # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/               # React components (10+)
│   │   ├── pages/                    # Page components
│   │   ├── services/                 # API client (api.ts)
│   │   ├── types/                    # TypeScript types
│   │   ├── App.tsx                   # Root component
│   │   ├── index.css                 # Global styles
│   │   └── main.tsx                  # App entry point
│   ├── public/                       # Static assets
│   ├── Dockerfile                    # Multi-stage build
│   ├── package.json                  # Dependencies
│   ├── vite.config.ts                # Vite configuration
│   ├── tailwind.config.js            # Tailwind CSS config
│   ├── tsconfig.json                 # TypeScript config
│   ├── .env                          # Environment variables
│   └── .gitignore                    # Git ignore rules
│
├── backend/                          # FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── api/dashboard.py          # Dashboard endpoints
│   │   ├── models/mission.py         # SQLAlchemy models
│   │   ├── services/                 # Business logic layer
│   │   ├── main.py                   # FastAPI app entry
│   │   ├── config.py                 # Configuration
│   │   ├── database.py               # Database connection
│   │   └── __init__.py
│   ├── Dockerfile                    # Production image
│   ├── requirements.txt              # Python dependencies
│   ├── .env                          # Environment variables
│   ├── README.md                     # Backend documentation
│   └── .gitignore                    # Git ignore rules
│
├── docker-compose.yml                # Multi-service orchestration
├── .env                              # Root environment (shared)
├── .gitignore                        # Project git ignore
├── README.md                         # This file
└── MIGRATION_GUIDE.md               # Setup instructions (legacy)
```

## 📋 Prerequisites

### Without Docker
- Python 3.10+
- Node.js 18+
- PostgreSQL 12+
- Grobid (optional, for PDF processing)

### With Docker (Recommended)
- Docker 20.10+
- Docker Compose 2.0+
- 8GB+ RAM (4GB for containers, 4GB for services)
- 20GB+ disk space

## 🔧 Installation & Deployment

### 1. Clone Repository

```bash
git clone <repository-url>
cd lhas
```

### 2. Configure Environment

```bash
# Copy and edit .env
cp .env.example .env

# Edit settings:
# - POSTGRES credentials
# - API keys (if needed)
# - Ports (if needed)
```

### 3. Using Docker Compose

```bash
# Build and start all services
docker compose up --build

# Or start in background
docker compose up -d --build

# View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres

# Stop services
docker compose down

# Stop and remove volumes (clean slate)
docker compose down -v
```

### 4. Verify Services

```bash
# Check service status
docker compose ps

# Test backend health
curl http://localhost:8000/health

# Test frontend
open http://localhost:3000

# API documentation
open http://localhost:8000/docs
```

## ⚙️ Configuration

### Environment Variables

#### Root `./.env`

```env
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=lhas
POSTGRES_PORT=5432

# Backend
ENVIRONMENT=production
DEBUG=false
BACKEND_PORT=8000
GROBID_URL=http://grobid:8070

# Frontend
FRONTEND_PORT=3000
NODE_ENV=production

# Grobid
GROBID_VERSION=0.8.0
GROBID_PORT=8070
```

### Service Configuration

**Backend** (`backend/app/config.py`):
- Reads from environment variables
- Auto-migrates database schema
- Configures async connection pooling
- Sets CORS for frontend

**Frontend** (`frontend/vite.config.ts`):
- Path aliases for imports
- TypeScript strict mode
- Tailwind CSS integration
- env var: `VITE_API_URL`

**Database** (`docker-compose.yml`):
- PostgreSQL 16 Alpine (minimal image)
- Automatic backups via volumes
- Health checks configured
- Connection pooling settings

### Docker Networking

Services communicate via internal Docker network using service names:

```
Frontend → Backend:   http://backend:8000
Backend → PostgreSQL: postgresql://postgres:5432/LHAS
Backend → Grobid:     http://grobid:8070
```

**Important:** Use service names, NOT localhost inside containers.

## 📚 API Documentation

### Base URL
- Development: `http://localhost:8000`
- Docker: `http://backend:8000`
- Production: `https://api.yourdomain.com`

### Interactive Docs
- **Swagger UI:** `/docs`
- **ReDoc:** `/redoc`
- **OpenAPI JSON:** `/openapi.json`

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health check |
| GET | `/api/dashboard/overview` | Dashboard statistics |
| GET | `/api/dashboard/missions` | List all missions |
| GET | `/api/dashboard/missions/{id}` | Mission details |
| GET | `/api/dashboard/missions/{id}/alerts` | Mission alerts |

### Example Requests

```bash
# Health check
curl http://localhost:8000/health

# Dashboard overview
curl http://localhost:8000/api/dashboard/overview

# Mission detail
curl http://localhost:8000/api/dashboard/missions/1

# API docs
open http://localhost:8000/docs
```

## 🔧 Troubleshooting

### Services Won't Start

**Check Docker:**
```bash
docker --version
docker compose --version
```

**Check permissions:**
```bash
# Ensure Docker daemon is running
docker ps
```

### Database Connection Error

```bash
# Verify PostgreSQL is running
docker compose logs postgres

# Check connection string
docker compose exec backend python -c "from app.config import settings; print(settings.DATABASE_URL)"

# Test connection
docker compose exec postgres psql -U postgres -d lhas -c "SELECT 1"
```

### Frontend Can't Connect to Backend

**Check CORS:**
```bash
# Verify backend CORS settings
docker compose logs backend | grep CORS

# Test API from frontend container
docker compose exec frontend curl http://backend:8000/health
```

**Check environment:**
```bash
# Verify VITE_API_URL in frontend
docker compose exec frontend printenv VITE_API_URL
```

### Port Already in Use

```bash
# Find process using port
lsof -i :3000          # Frontend
lsof -i :8000          # Backend
lsof -i :5432          # PostgreSQL

# Kill process (Unix/Mac)
kill -9 <PID>

# Kill process (Windows)
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

### Clear Everything & Start Fresh

```bash
# Stop and remove all containers, volumes, networks
docker compose down -v

# Remove images
docker compose down -v --rmi all

# Rebuild and start
docker compose up --build
```

## 🏭 Production Deployment

### Pre-Production Checklist

- [ ] Update `.env` with production credentials
- [ ] Set `ENVIRONMENT=production` and `DEBUG=false`
- [ ] Configure PostgreSQL with managed service (AWS RDS, Google Cloud SQL, etc.)
- [ ] Setup SSL/TLS certificates
- [ ] Configure backup strategy
- [ ] Setup monitoring and logging
- [ ] Configure secrets management (not in .env)
- [ ] Setup CI/CD pipeline
- [ ] Load testing and performance tuning

### Production Environment Variables

```env
# Use strong passwords
POSTGRES_PASSWORD=<strong-random-password>

# Production mode
ENVIRONMENT=production
DEBUG=false

# External services
DATABASE_URL=postgresql://user:password@rds.amazonaws.com/lhas
GROBID_URL=http://grobid-service:8070

# Security
CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
```

### Deployment Platforms

**AWS ECS:**
```bash
# Push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker tag lhas-backend:latest <account-id>.dkr.ecr.<region>.amazonaws.com/lhas-backend:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/lhas-backend:latest
```

**Google Cloud Run:**
```bash
gcloud builds submit --tag gcr.io/<project>/lhas-backend
gcloud run deploy lhas-backend --image gcr.io/<project>/lhas-backend
```

**Kubernetes:**
```bash
# Create deployment from docker-compose
kompose convert -f docker-compose.yml -o k8s/

# Deploy
kubectl apply -f k8s/
```

## 📊 Performance Tuning

### Database
- Connection pool size: 20 (dev), 100+ (prod)
- Enable query logging for optimization
- Create indexes on frequently queried columns
- Archive old alert records

### Backend
- Enable uvicorn workers: `--workers 4`
- Use gunicorn for production: `gunicorn -w 4 -b 0.0.0.0:8000 app.main:app`
- Configure timeout settings
- Enable caching layer (Redis)

### Frontend
- Bundle size: Currently ~200KB (gzipped)
- Lazy load components
- Use service worker for offline support
- CDN for static assets

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -am "Add feature"`
3. Push to branch: `git push origin feature/your-feature`
4. Submit pull request

## 📖 Additional Documentation

- [Backend README](./backend/README.md) - API details & setup
- [Frontend README](./frontend/README.md) - Component documentation
- [Migration Guide](./MIGRATION_GUIDE.md) - Separation guide

## 📝 License

MIT

## 🆘 Support

For issues or questions:
1. Check [Troubleshooting](#troubleshooting) section
2. Review logs: `docker compose logs <service>`
3. Check API docs: http://localhost:8000/docs
4. Open an issue: <repository-issues>

## 🎯 Quick Commands Reference

```bash
# Start services
docker compose up -d --build

# Stop services
docker compose down

# View logs
docker compose logs -f

# Execute command in container
docker compose exec backend bash
docker compose exec frontend bash

# Rebuild specific service
docker compose up --build -d backend

# Remove all data (clean slate)
docker compose down -v

# Health check
curl http://localhost:8000/health

# Database shell
docker compose exec postgres psql -U postgres -d lhas

# Frontend shell
docker compose exec frontend ash

# View running services
docker compose ps
```

## 🗓️ Version History

- **v1.0.0** (2026-03-27) - Initial production-ready release
  - Full Docker setup
  - PostgreSQL integration
  - Grobid PDF parsing
  - React mission control UI
  - FastAPI backend

---

**Built with ❤️ for research mission tracking**
