# Frontend & Backend Separation & Migration Guide

This document explains how to separate the LHAS frontend and backend for containerization.

## Project Structure After Migration

```
final/
├── frontend/                    # React/Vite frontend
│   ├── src/
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── Dockerfile               # Frontend Docker image
│   ├── .env.example
│   ├── .gitignore
│   └── README.md
│
├── backend/                     # FastAPI backend
│   ├── app/
│   ├── requirements.txt
│   ├── Dockerfile               # Backend Docker image
│   ├── docker-compose.yml       # Full stack compose
│   ├── .env.example
│   ├── .gitignore
│   └── README.md
│
└── docker-compose.yml          # Root compose (optional, orchestrates both)
```

## Step 1: Move Frontend Files

Move all current frontend files (except backend/) to the `frontend/` directory:

```bash
cd final

# Create frontend directory if not exists
mkdir -p frontend

# Copy frontend files
cp -r src frontend/
cp -r public frontend/
cp index.html frontend/
cp package.json frontend/
cp package-lock.json frontend/
cp vite.config.ts frontend/
cp tsconfig.json frontend/
cp tsconfig.app.json frontend/
cp tsconfig.node.json frontend/
cp eslint.config.js frontend/
cp tailwind.config.js frontend/
cp postcss.config.js frontend/
cp .gitignore frontend/
cp App.css frontend/src/  # Ensure App.css is in frontend/src/
```

## Step 2: Setup Frontend Environment

```bash
cd frontend

# Create .env file
cat > .env << EOF
# Frontend Environment Configuration
VITE_API_URL=http://localhost:8000
EOF

# Or for production:
cat > .env.production << EOF
VITE_API_URL=https://api.yourdomain.com
EOF
```

## Step 3: Update Frontend to Use Backend API

In your React components (e.g., `HomeScreen.tsx`), replace mock data with API calls:

### Before (Mock Data):
```typescript
const mockMissions: Mission[] = [
  { id: '1', name: 'COVID-19 Long-term Effects', ... },
  // ...
];
```

### After (API Data):
```typescript
import { apiClient, type DashboardOverview, type Mission } from '@/services/api';

export const HomeScreen: React.FC = () => {
  const [dashboardData, setDashboardData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const data = await apiClient.getDashboardOverview();
        setDashboardData(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!dashboardData) return <div>No data</div>;

  const { stats, alerts, missions } = dashboardData;
  // Use stats, alerts, missions in your components
};
```

## Step 4: Setup Backend Environment

```bash
cd backend

# Create .env file
cat > .env << EOF
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lhas
SQL_ECHO=false
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,https://yourdomain.com
EOF
```

## Step 5: Run Services Separately (Development)

### Terminal 1 - Backend:
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run server
python -m app.main
```

Backend will start at: `http://localhost:8000`
API Docs: `http://localhost:8000/docs`

### Terminal 2 - Frontend:
```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

Frontend will start at: `http://localhost:5173`

## Step 6: Docker Containerization

### Build Individual Images

Backend:
```bash
cd backend
docker build -t lhas-backend:latest .
```

Frontend:
```bash
cd frontend
docker build -t lhas-frontend:latest .
```

### Run with Docker Compose

From the backend directory:
```bash
cd backend
docker-compose up -d
```

This will start:
- PostgreSQL: `localhost:5432`
- Backend API: `localhost:8000`
- Frontend: `localhost:5173` (if included)

## Step 7: Environment Variables

### Frontend (.env files)
```
# .env.development
VITE_API_URL=http://localhost:8000

# .env.production
VITE_API_URL=https://api.yourdomain.com
```

### Backend (.env files)
```
# .env.development
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lhas
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# .env.production
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://user:password@prod-db:5432/lhas
CORS_ORIGINS=https://yourdomain.com
```

## Step 8: Database Setup

The backend automatically creates tables on first run via SQLAlchemy.

To manually initialize the database after PostgreSQL is running:

```bash
cd backend
python

# In Python shell:
import asyncio
from app.database import init_db
asyncio.run(init_db())
exit()
```

## File Organization Summary

### Original (Monolithic):
```
final/
├── src/
├── public/
├── package.json
└── ... (all files mixed)
```

### After Migration (Separated):
```
final/
├── frontend/           # Isolated frontend
│   ├── src/
│   ├── package.json
│   └── Dockerfile
├── backend/            # Isolated backend
│   ├── app/
│   ├── requirements.txt
│   └── Dockerfile
└── docker-compose.yml  # Orchestrates both
```

## Troubleshooting

### Frontend Can't Connect to Backend
- Check backend is running on `http://localhost:8000`
- Check `VITE_API_URL` in `.env`
- Check browser console for CORS errors
- Verify `CORS_ORIGINS` in backend `.env` includes frontend URL

### Database Connection Error
- Verify PostgreSQL is running
- Check `DATABASE_URL` in backend `.env`
- Ensure database exists: `createdb lhas`

### Port Already in Use
```bash
# Find process using port 5432 (PostgreSQL)
lsof -i:5432
kill -9 <PID>

# Find process using port 8000 (Backend)
lsof -i:8000
kill -9 <PID>

# Find process using port 5173 (Frontend)
lsof -i:5173
kill -9 <PID>
```

## Next Steps

1. Migrate frontend to `frontend/` directory
2. Update Home Screen component to use API client
3. Setup backend database
4. Test full integration
5. Configure Docker for production
6. Setup CI/CD pipeline

## API Integration Example

See `src/services/api.ts` for the complete API client implementation.

Usage:
```typescript
import { apiClient } from '@/services/api';

// Get dashboard data
const data = await apiClient.getDashboardOverview();

// Get mission details
const mission = await apiClient.getMissionDetail(missionId);

// Get mission alerts
const alerts = await apiClient.getMissionAlerts(missionId);

// Check health
const health = await apiClient.getHealth();
```
