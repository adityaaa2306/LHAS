# Docker Setup Guide - LHAS

Complete Docker and Docker Compose setup instructions for production deployment.

## Table of Contents

1. [Requirements](#requirements)
2. [Initial Setup](#initial-setup)
3. [Running Services](#running-services)
4. [Service Management](#service-management)
5. [Troubleshooting](#troubleshooting)
6. [Production Deployment](#production-deployment)
7. [Scaling & Performance](#scaling--performance)

## Requirements

### System Requirements

- **Docker**: 20.10+ (with containerd runtime)
- **Docker Compose**: 2.0+
- **RAM**: 8GB minimum (4GB for containers + system)
- **Disk**: 20GB free space (10GB for images + data volumes)
- **OS**: Windows (WSL2), macOS, or Linux
- **CPU**: 2 cores minimum, 4+ cores recommended

### Verify Installation

```bash
# Check Docker installation
docker --version
# Expected: Docker version 20.10.0 or higher

# Check Docker Compose installation
docker compose version
# Expected: Docker Compose version 2.0.0 or higher

# Verify Docker daemon is running
docker ps
# Should show: CONTAINER ID IMAGE COMMAND ... STATUS PORTS NAMES
```

## Initial Setup

### Step 1: Clone and Navigate

```bash
git clone <repository-url>
cd lhas
```

### Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your preferences
# Windows: notepad .env
# Mac/Linux: vim .env or nano .env

# Key variables to configure:
# - POSTGRES_PASSWORD (change from 'postgres' in production)
# - ENVIRONMENT (development or production)
# - BACKEND_PORT, FRONTEND_PORT, GROBID_PORT (if needed)
```

### Step 3: Verify Project Structure

```bash
# Check required directories exist
ls -la
# Should show: backend/ frontend/ docker-compose.yml .env README.md

# Verify backend files
ls backend/app/
# Should show: models/ services/ api/ main.py config.py database.py __init__.py

# Verify frontend files
ls frontend/src/
# Should show: components/ pages/ services/ types/ App.tsx main.tsx
```

## Running Services

### Quick Start

```bash
# Start all services in the background
docker compose up -d --build

# This will:
# 1. Build frontend Docker image (from frontend/Dockerfile)
# 2. Build backend Docker image (from backend/Dockerfile)
# 3. Pull PostgreSQL 16 and Grobid 0.8.0 images
# 4. Create Docker network (lhas-network)
# 5. Create volumes for database and backend storage
# 6. Start all 4 services in background
```

### Monitor Startup

```bash
# Watch logs from all services
docker compose logs -f

# Or specific service:
docker compose logs -f backend       # Backend API
docker compose logs -f frontend      # Frontend
docker compose logs -f postgres      # Database
docker compose logs -f grobid        # PDF parser

# Press Ctrl+C to stop watching logs
```

### Wait for Services to Be Ready

```bash
# Check service health
docker compose ps

# Expected status:
# SERVICE      STATUS                  PORTS
# postgres     Up ... (healthy)
# backend      Up ... (healthy)
# frontend     Up ... (healthy)
# grobid       Up ... (healthy)

# All should show (healthy) once ready
```

### Access Services

Once services are running:

- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **API ReDoc**: http://localhost:8000/redoc
- **Grobid**: http://localhost:8070
- **Database**: `localhost:5432`

### Test Connectivity

```bash
# Test backend health
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"1.0.0"}

# Test dashboard API
curl http://localhost:8000/api/dashboard/overview
# Expected: {"stats":{...},"alerts":[...],"missions":[...]}

# Test frontend (should return HTML)
curl http://localhost:3000
# Expected: Page HTML content

# Test Grobid
curl http://localhost:8070/api/isalive
# Expected: {"version":"0.8.0","isAlive":true}
```

## Service Management

### Stop Services

```bash
# Stop all services (keep volumes and networks)
docker compose stop

# Restart stopped services
docker compose start

# Stop specific service
docker compose stop backend
docker compose start backend
```

### Remove Services

```bash
# Stop and remove containers, networks (keep volumes)
docker compose down

# Stop and remove everything including volumes
docker compose down -v

# Stop and remove images too
docker compose down -v --rmi all
```

### View Logs

```bash
# All services
docker compose logs

# Last 100 lines
docker compose logs --tail=100

# Follow logs (live)
docker compose logs -f

# Specific service
docker compose logs backend
docker compose logs postgres

# By timestamp
docker compose logs --since 10m
docker compose logs --until 5m

# With timestamps
docker compose logs -t
```

### Execute Commands in Containers

```bash
# Open bash shell in backend container
docker compose exec backend bash

# Open shell in frontend container
docker compose exec frontend ash

# Open postgres shell in database
docker compose exec postgres psql -U postgres -d lhas

# Run Python script in backend
docker compose exec backend python -c "print('Hello')"

# Check environment variables in container
docker compose exec backend env
```

### View Container Processes

```bash
# Active containers
docker compose ps

# Show all status including stopped
docker compose ps -a

# CPU and memory usage
docker stats

# Network information
docker network ls
docker network inspect lhas-network
```

## Troubleshooting

### Common Issues

#### 1. Services Won't Start

**Error**: `docker: command not found`

**Solution**:
```bash
# Install Docker
# Windows: https://docs.docker.com/desktop/install/windows-install/
# Mac: https://docs.docker.com/desktop/install/mac-install/
# Linux: https://docs.docker.com/engine/install/

# Verify installation
docker --version
```

#### 2. Port Already in Use

**Error**: `Error starting container: port 3000 already in use`

**Solution**:
```bash
# Find what's using the port
lsof -i :3000              # Mac/Linux
netstat -ano | findstr :3000  # Windows

# Kill the process
kill -9 <PID>              # Mac/Linux
taskkill /PID <PID> /F     # Windows

# Or change port in .env
FRONTEND_PORT=3001
docker compose up -d --build
```

#### 3. Database Connection Error

**Error**: `could not connect to server: Connection refused`

**Solution**:
```bash
# Check postgres is running
docker compose ps postgres
# Should show "Up"

# Check postgres logs
docker compose logs postgres

# Verify connection
docker compose exec postgres psql -U postgres -d lhas -c "SELECT 1"

# Reset database
docker compose down -v
docker compose up -d postgres
```

#### 4. Frontend Can't Connect to Backend

**Error**: API requests fail, CORS errors in browser console

**Solution**:
```bash
# Verify backend is running
docker compose exec backend curl http://localhost:8000/health

# Check frontend env variable
docker compose exec frontend env | grep VITE_API_URL
# Should show: VITE_API_URL=http://backend:8000

# Test from frontend container
docker compose exec frontend wget -O - http://backend:8000/health

# Check CORS configuration
docker compose logs backend | grep CORS
```

#### 5. Container Exits Immediately

**Error**: Container starts then stops

**Solution**:
```bash
# Check the logs for error
docker compose logs backend

# Common issues:
# - Invalid environment variables
# - Port already in use
# - Volume permission error
# - Dockerfile error

# If backend: check database is ready
docker compose logs postgres | head -20

# If frontend: check node_modules
docker compose exec frontend ls -la node_modules
```

#### 6. Database Data Persists When Not Wanted

**Solution**:
```bash
# Remove volume completely
docker compose down -v

# This removes all databases and data
# Everything fresh on next start
```

#### 7. Out of Disk Space

**Solution**:
```bash
# Clean up Docker
docker system prune -a

# Remove unused volumes
docker volume prune

# Remove unused networks
docker network prune

# Check disk usage
docker system df
```

### Debug Commands

```bash
# Check service startup errors
docker compose logs --tail=50 <service>

# Inspect container
docker inspect lhas-backend

# Check running processes in container
docker top lhas-backend

# Mount a shell into container
docker compose exec backend bash

# Copy files from/to container
docker compose cp backend:/app/storage/file.txt ./
docker compose cp ./file.txt backend:/app/storage/

# Check network connectivity
docker compose exec backend ping grobid
docker compose exec backend curl http://postgres:5432
```

## Production Deployment

### Pre-Production Checklist

- [ ] Test with production environment: `ENVIRONMENT=production DEBUG=false`
- [ ] Update PostgreSQL credentials (not postgres:postgres)
- [ ] Configure external database (AWS RDS, GCP Cloud SQL, or similar)
- [ ] Setup SSL/TLS certificates
- [ ] Configure backup strategy
- [ ] Setup monitoring (Datadog, New Relic, Prometheus)
- [ ] Configure log aggregation (ELK, Datadog, Splunk)
- [ ] Load test with expected traffic
- [ ] Setup CI/CD pipeline
- [ ] Configure secrets management (AWS Secrets Manager, Vault)
- [ ] Document runbooks for incidents

### Production Environment

```env
# .env for production
ENVIRONMENT=production
DEBUG=false
SQL_ECHO=false

# Strong credentials
POSTGRES_USER=lhas_admin
POSTGRES_PASSWORD=<generate-strong-password>

# External database (example: AWS RDS)
# DATABASE_URL=postgresql+asyncpg://user:password@prod-db.aws.com:5432/lhas

# Restrict CORS
CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

# Monitoring
SENTRY_DSN=https://your-sentry-dsn
DATADOG_API_KEY=your-datadog-key
```

### Deployment Platforms

#### AWS ECS with ECR

```bash
# Push images to AWS ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker tag lhas-backend:latest <account>.dkr.ecr.us-east-1.amazonaws.com/lhas-backend:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/lhas-backend:latest

# Deploy with ECS CLI or CloudFormation
```

#### Google Cloud Run / Compute Engine

```bash
# Push to Google Container Registry
docker tag lhas-backend:latest gcr.io/<project>/lhas-backend:latest
docker push gcr.io/<project>/lhas-backend:latest

# Deploy to Cloud Run
gcloud run deploy lhas-backend --image gcr.io/<project>/lhas-backend:latest
```

#### Kubernetes

```bash
# Convert docker-compose to Kubernetes manifests
kompose convert -f docker-compose.yml -o k8s/

# Apply to cluster
kubectl apply -f k8s/

# Scale services
kubectl scale deployment/backend --replicas=3
```

#### DigitalOcean App Platform

```bash
# Connect to DigitalOcean
doctl auth init

# Deploy docker-compose
doctl apps create --spec app.yaml

# Where app.yaml contains your services
```

### Self-Hosted / VPS

```bash
# 1. SSH into server
ssh user@your-server.com

# 2. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. Clone repository
git clone <repo-url>
cd lhas

# 4. Configure environment
cp .env.example .env
# Edit .env with production values

# 5. Build images
docker compose build

# 6. Start services
docker compose up -d

# 7. Setup SSL with Let's Encrypt
# Install certbot and configure nginx
```

## Scaling & Performance

### Horizontal Scaling

```bash
# Scale backend services (requires load balancer)
docker compose up -d --scale backend=3

# Each backend container connects to same database
# Load balancer distributes traffic
```

### Performance Tuning

```env
# .env - Performance settings

# Database
DB_POOL_SIZE=100        # Increase for high concurrency
DB_MAX_OVERFLOW=200

# Backend workers (if using Gunicorn)
# See backend/Dockerfile CMD

# Grobid memory (large document processing)
GROBID_JAVA_OPTS=-Xmx8G

# Frontend: CDN for static assets
# Configure in production reverseoxy
```

### Monitoring

```bash
# Monitor resource usage
docker stats

# Check container health
docker compose ps
# All should show (healthy)

# Monitor logs for errors
docker compose logs --since 1h | grep ERROR
```

### Backup Strategy

```bash
# Backup database
docker compose exec postgres pg_dump -U postgres lhas > backup.sql

# Backup volumes
# For production, use cloud backups (AWS S3, GCS, etc)

# Restore database
docker compose exec -T postgres psql -U postgres < backup.sql
```

### Security Best Practices

```bash
# Use secrets management
# - Don't store credentials in .env (production)
# - Use environment variables from secure vault
# - Rotate credentials regularly

# Network security
# - Use VPCs/private networks for databases
# - Restrict database access by IP
# - Use SSL/TLS for all connections

# Image security
# - Scan images for vulnerabilities
# - Use minimal base images (alpine, slim)
# - Keep images updated

# General security
# - Use strong CORS policies
# - Enable rate limiting
# - Setup WAF (Web Application Firewall)
# - Monitor access logs
```

## Quick Reference

```bash
# Start services
docker compose up -d --build

# Stop services
docker compose down

# View logs
docker compose logs -f

# Execute command
docker compose exec backend bash

# Rebuild specific service
docker compose up -d --build backend

# Fresh start (remove data)
docker compose down -v && docker compose up -d --build

# Health check
docker compose ps

# Database shell
docker compose exec postgres psql -U postgres -d lhas

# Backend shell
docker compose exec backend bash

# Frontend shell
docker compose exec frontend ash
```

---

For more information, see:
- [README.md](../README.md) - Main documentation
- [.env.example](../.env.example) - Configuration options
- [backend/README.md](../backend/README.md) - Backend setup
