# LHAS Docker Architecture Guide

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Local Developer Machine                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │              Docker Engine (Daemon)                               │   │
│  │                                                                    │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │         Docker Bridge Network: lhas-network                 │ │   │
│  │  │         (172.28.0.0/16)                                     │ │   │
│  │  │                                                              │ │   │
│  │  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐  │ │   │
│  │  │  │   Frontend       │  │    Backend       │  │ PostgreSQL   │ │   │
│  │  │  │   Container      │  │    Container     │  │ Container    │ │   │
│  │  │  │                  │  │                  │  │              │ │   │
│  │  │  │  Node.js 18      │  │  Python 3.11     │  │  PG 16       │ │   │
│  │  │  │  Port 3000       │─→│  Port 8000       │─→│  Port 5432   │ │   │
│  │  │  │                  │  │                  │  │              │ │   │
│  │  │  │ * React 19       │  │ * FastAPI        │  │ * 20GB       │ │   │
│  │  │  │ * Vite build     │  │ * SQLAlchemy     │  │   storage    │ │   │
│  │  │  │ * Tailwind CSS   │  │ * async/await    │  │ * Volume:    │ │   │
│  │  │  │ * TypeScript     │  │ * Pydantic       │  │   pg_data    │ │   │
│  │  │  │ * serve static   │  │ * uvicorn        │  │              │ │   │
│  │  │  │                  │  │                  │  │              │ │   │
│  │  │  └──────────────────┘  └──────────────────┘  └──────────────┘ │   │
│  │  │                                    │                           │   │
│  │  │                                    └─────────────────┐         │   │
│  │  │                                                      ▼         │   │
│  │  │                                             ┌──────────────┐  │   │
│  │  │                                             │   Grobid     │  │   │
│  │  │                                             │  Container   │  │   │
│  │  │                                             │              │  │   │
│  │  │                                             │ Grobid 0.8.0 │  │   │
│  │  │                                             │ Port 8070    │  │   │
│  │  │                                             │              │  │   │
│  │  │                                             │ * PDF parse  │  │   │
│  │  │                                             │ * JVM 4GB    │  │   │
│  │  │                                             │ * Volume:    │  │   │
│  │  │                                             │   grobid_    │  │   │
│  │  │                                             │   models     │  │   │
│  │  │                                             │              │  │   │
│  │  │                                             └──────────────┘  │   │
│  │  │                                                               │   │
│  │  │ Volumes (Persistent Storage):                                │   │
│  │  │ ──────────────────────────────                               │   │
│  │  │ • postgres_data      (Database tables)                       │   │
│  │  │ • backend_storage    (Uploads, indices)                      │   │
│  │  │ • grobid_models      (ML models)                             │   │
│  │  │                                                              │   │
│  │  │ Networks (Docker DNS resolution):                            │   │
│  │  │ ──────────────────────────────────                           │   │
│  │  │ • frontend hostname → frontend container IP                  │   │
│  │  │ • backend hostname  → backend container IP                   │   │
│  │  │ • postgres hostname → postgres container IP                  │   │
│  │  │ • grobid hostname   → grobid container IP                    │   │
│  │  │                                                              │   │
│  │  └──────────────────────────────────────────────────────────────┘ │   │
│  │                                                                    │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Host Ports Exposed:                                                       │
│  ├─ 3000   → Frontend container:3000                                       │
│  ├─ 8000   → Backend container:8000                                        │
│  ├─ 5432   → PostgreSQL container:5432                                     │
│  └─ 8070   → Grobid container:8070                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Service Communication Flow

### 1. Frontend to Backend

```
User Browser
    ↓
http://localhost:3000 (Host Port)
    ↓
[Docker Bridge]
    ↓
Frontend Container (port 3000)
    ↓
fetch/axios call to 'http://backend:8000'
    ↓
[Docker DNS Resolution]
'backend' → backend container IP address
    ↓
Backend Container (port 8000)
    ↓
FastAPI Application
```

### 2. Backend to Database

```
FastAPI Application
    ↓
SQLAlchemy ORM
    ↓
asyncpg driver
    ↓
PostgreSQL URL: 'postgresql+asyncpg://postgres:aditya@postgres:5432/LHAS'
    ↓
[Docker DNS Resolution]
'postgres' → postgres container IP address
    ↓
PostgreSQL Container (port 5432)
    ↓
Query execution → Results back
```

### 3. Backend to Grobid

```
Backend Service
    ↓
PDF Upload Endpoint
    ↓
HTTP Request to 'http://grobid:8070/api/processFulltextDocument'
    ↓
[Docker DNS Resolution]
'grobid' → grobid container IP address
    ↓
Grobid Container (port 8070)
    ↓
PDF Processing → Extracted Data
```

## Container Specifications

### Frontend Container

```yaml
Name: lhas-frontend
Image: lhas-frontend:latest (local build)
Base: node:18-alpine (75MB)

Ports:
  - 3000:3000 (HTTP)

Volumes:
  - none (stateless)

Environment:
  - VITE_API_URL=http://backend:8000
  - NODE_ENV=production

Resources:
  - CPU: 1 core (can share)
  - Memory: 100-300MB

Health Check:
  - Endpoint: GET http://localhost:3000
  - Interval: 30s
  - Timeout: 10s
```

### Backend Container

```yaml
Name: lhas-backend
Image: lhas-backend:latest (local build)
Base: python:3.11-slim (150MB)

Ports:
  - 8000:8000 (HTTP)

Volumes:
  - backend_storage:/app/storage

Environment:
  - DATABASE_URL=postgresql+asyncpg://postgres:aditya@postgres:5432/LHAS
  - ENVIRONMENT=production
  - GROBID_URL=http://grobid:8070
  - CORS_ORIGINS=...

Resources:
  - CPU: 2 cores (shared)
  - Memory: 500MB-1GB

Health Check:
  - Endpoint: GET http://localhost:8000/health
  - Interval: 30s
  - Timeout: 10s
```

### PostgreSQL Container

```yaml
Name: lhas-postgres
Image: postgres:16-alpine (80MB)

Ports:
  - 5432:5432 (PostgreSQL)

Volumes:
  - postgres_data:/var/lib/postgresql/data
  - init-db.sql:/docker-entrypoint-initdb.d/init.sql

Environment:
  - POSTGRES_USER=postgres
  - POSTGRES_PASSWORD=postgres
  - POSTGRES_DB=LHAS

Resources:
  - CPU: 1-2 cores
  - Memory: 500MB-2GB

Data:
  - Tables: missions, sessions, alerts
  - Connections: 20+ pooled
  - Storage: Grows with data

Backup:
  - Via named volume (docker managed)
  - Manual: docker compose exec postgres pg_dump ...
```

### Grobid Container

```yaml
Name: lhas-grobid
Image: lfoppiano/grobid:0.8.0 (500MB)

Ports:
  - 8070:8070 (HTTP)

Volumes:
  - grobid_models:/opt/grobid/grobid-home/models

Environment:
  - JAVA_OPTS=-Xmx4G

Resources:
  - CPU: 2 cores
  - Memory: 4GB (Java heap)

Functions:
  - PDF text extraction
  - Metadata parsing
  - Reference extraction
  - Table parsing

Startup:
  - Time: 30-60 seconds
  - Disease: Loads ML models from volume
```

## Volume Management

### postgres_data

```
Location: Docker-managed (/var/lib/docker/volumes/...)
Contents: PostgreSQL database files
Size: Grows with data (starts ~50MB)
Persistence: Survives container restart
Cleanup: docker compose down -v (deletes all data)
Backup: docker compose exec postgres pg_dump
```

### backend_storage

```
Location: Docker-managed
Contents: 
  - Uploaded PDF files
  - FAISS indices
  - Generated embeddings
  - Intermediate processing files
Size: Depends on document corpus
Persistence: Survives container restart
Cleanup: docker compose down -v (deletes all files)
```

### grobid_models

```
Location: Docker-managed
Contents: Machine learning models for Grobid
Size: ~200MB
Persistence: Survives container restart
Note: Changes in volume persist between restarts
```

## Network Details

### Docker Bridge Network: lhas-network

```
Configuration:
  - Driver: bridge
  - Subnet: 172.28.0.0/16
  - Type: User-defined (not default)

Advantages:
  - Built-in DNS resolution
  - Service discovery by name
  - Automatic /etc/hosts updating
  - Network isolation
  - Container auto-connect

DNS Resolution:
  Container A → http://backend:8000
  Docker internal DNS resolves 'backend' to backend container's IP

Isolation:
  - Separate from host network
  - Other docker networks cannot access
  - Only containers in lhas-network can communicate
```

## Environment Variable Flow

```
1. Root .env file
   └─→ Loaded by docker-compose.yml

2. Docker Compose
   └─→ Sets environment for each service

3. Service Container
   ├─→ Backend reads: DATABASE_URL, GROBID_URL, CORS_ORIGINS
   ├─→ Frontend reads: VITE_API_URL
   └─→ PostgreSQL reads: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

4. Application
   └─→ Runtime configuration from environment
```

## Typical Startup Sequence

```
1. docker compose up -d --build
   ├─ Builds frontend image (if Dockerfile changed)
   ├─ Builds backend image (if Dockerfile changed)
   ├─ Creates volumes (postgres_data, backend_storage, grobid_models)
   ├─ Creates network (lhas-network)
   └─ Starts containers in order

2. PostgreSQL starts first
   ├─ Initializes database server
   ├─ Creates 'LHAS' database
   ├─ Awaits connections
   └─ Reports ready (healthy) when pg_isready succeeds

3. Backend waits for PostgreSQL
   ├─ Depends on postgres:service_healthy
   ├─ Once postgres ready, backend starts
   ├─ Connects to PostgreSQL
   ├─ Auto-creates tables via SQLAlchemy
   ├─ Starts uvicorn server
   └─ Reports ready (healthy) when /health endpoint responds

4. Grobid starts independently
   ├─ JVM loads models from volume
   ├─ Initializes REST API
   └─ Reports ready (healthy) when /api/isalive responds

5. Frontend waits for Backend
   ├─ Depends on backend service
   ├─ Once backend ready, frontend starts
   ├─ Builds static assets (already done in Dockerfile)
   ├─ Serves with 'serve' package
   └─ Ready on port 3000

6. All healthy
   └─ Services accessible on host ports
```

## Debugging Container Networking

```bash
# From inside backend container:
docker compose exec backend sh

# Then run:
ping postgres          # Test DNS resolution
curl http://postgres:5432  # Test connection
curl http://grobid:8070/api/isalive  # Test Grobid

# From Docker host:
docker network inspect lhas-network  # See connected containers
docker network ls            # List all networks
```

## Production Scaling Considerations

### Current Single-Machine Setup
- All containers on one Docker host
- Suitable for: Dev, staging, small production (<1000 requests/day)

### Scaling to Multiple Machines

**Option 1: Docker Swarm**
```bash
docker swarm init
docker stack deploy -c docker-compose.yml lhas
```

**Option 2: Kubernetes**
```bash
kompose convert -f docker-compose.yml -o k8s/
kubectl apply -f k8s/
```

### Scaling Considerations

- **Database**: Move to managed service (AWS RDS, GCP Cloud SQL)
- **File Storage**: Move to S3 or cloud equivalent
- **Frontend**: Use CDN (CloudFront, Akamai)
- **Backend**: Load balance across multiple instances
- **Grobid**: Optional dedicated service or AWS Textract
- **Caching**: Add Redis layer for frequently accessed data

---

For more information:
- [README.md](../README.md) - Main documentation
- [DOCKER_SETUP.md](../DOCKER_SETUP.md) - Detailed Docker setup
- [.env.example](../.env.example) - Configuration options
