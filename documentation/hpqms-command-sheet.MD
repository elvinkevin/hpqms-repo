# HPQMS Command Cheat Sheet

## 1. 🐳 Docker — commands you'll use most

### Start the whole system

```powershell
docker compose up -d
```

Starts PostgreSQL + backend in the background.

### Start and rebuild after changing Dockerfile/dependencies

```powershell
docker compose up -d --build
```

Use this when you've changed:

* `Dockerfile`
* `requirements.txt`
* files being copied into the image
* Docker configuration

### See running containers

```powershell
docker compose ps
```

### See live logs

```powershell
docker compose logs -f
```

Only backend:

```powershell
docker compose logs -f backend
```

Only PostgreSQL:

```powershell
docker compose logs -f postgres
```

Press `Ctrl + C` to stop following logs.

### Stop containers

```powershell
docker compose stop
```

This stops them but preserves everything.

### Start stopped containers again

```powershell
docker compose start
```

### Stop and remove containers/network

```powershell
docker compose down
```

**Important:** this does NOT normally delete your PostgreSQL volume.

---

## 2. 🗄️ Database commands

Your Docker database is:

```
Database: hpqms
User:     hpqms
Password: hpqms_dev_password
Container: hpqms-postgres
```

### See database tables

```powershell
docker exec hpqms-postgres psql -U hpqms -d hpqms -c "\dt"
```

This is a useful sanity check.

### Open PostgreSQL interactively

```powershell
docker exec -it hpqms-postgres psql -U hpqms -d hpqms
```

Then you can run:

```sql
\dt
```

or:

```sql
SELECT * FROM departments;
```

Exit with:

```sql
\q
```

### Run a SQL query without entering PostgreSQL

For example:

```powershell
docker exec hpqms-postgres psql -U hpqms -d hpqms -c "SELECT * FROM departments;"
```

---

## 3. 🌱 Seeding the database

After we've added `seed.py` to your Docker image:

```powershell
docker exec hpqms-backend python seed.py
```

That's the command you'll use to seed the Docker database.

On a fresh development database, the seed creates the first administrator if one does not already exist:

- Employee ID: `ADMIN001`
- Password: `AdminAccess123!`
- Role: `ADMIN`

Sign in from the staff login page. Admin accounts open the dashboard directly and do not need a service-point check-in. Re-running the seed will not reset an existing admin password. These are development-only credentials; change the password after first use. In non-development environments, provide `INITIAL_ADMIN_EMPLOYEE_ID` and `INITIAL_ADMIN_PASSWORD` as environment settings before seeding.

If you change the seed script, rebuild first:

```powershell
docker compose up -d --build
```

then:

```powershell
docker exec hpqms-backend python seed.py
```

---

## 4. 🔄 Reset the Docker database

This one is **important**.

If you want a completely fresh PostgreSQL database:

```powershell
docker compose down -v
```

Then:

```powershell
docker compose up -d --build
```

The `-v` removes the PostgreSQL Docker volume.

So:

```
docker compose down
```

= stop/remove containers, **keep database**

while:

```
docker compose down -v
```

= remove containers **and delete database volume**

### ⚠️ Treat `down -v` as destructive

It wipes your Docker database.

For your testing workflow, though, this is very useful:

```powershell
docker compose down -v
docker compose up -d --build
docker exec hpqms-backend python seed.py
```


docker build -t your-dockerhub-username/hpqms-backend:latest -f backend/Dockerfile .
docker push your-dockerhub-username/hpqms-backend:latest

That gives you:

```
Fresh PostgreSQL
       ↓
Alembic migrations
       ↓
Empty HPQMS schema
       ↓
Seed departments/staff/service points
       ↓
Ready for testing
```

---

## 5. 🧱 Alembic migrations

### Check current migration

Inside your backend container:

```powershell
docker exec hpqms-backend alembic current
```

### See migration history

```powershell
docker exec hpqms-backend alembic history
```

### Apply migrations

Normally Docker does this automatically because your Compose command contains:

```
alembic upgrade head
```

But manually:

```powershell
docker exec hpqms-backend alembic upgrade head
```

### Create a migration

When you've changed SQLAlchemy models:

```powershell
docker exec hpqms-backend alembic revision --autogenerate -m "describe your change"
```

Then inspect the generated migration **before** applying it.

Apply:

```powershell
docker exec hpqms-backend alembic upgrade head
```

---

## 6. 🐍 Local Python development

When working outside Docker and using your Windows virtual environment:

Activate it:

```powershell
.\backend\venv\Scripts\Activate.ps1
```

You should see:

```
(venv)
```
COMMAND FOR CLEARING THE DATABASE CLEANLY WITHOUT DROPPING THE EXISTING DATABASE TABLES TO AVOID ALEMBIC MIGRATION CONFLICTS

DO $$ 
DECLARE 
    r RECORD;
BEGIN 
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP 
        EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE'; 
    END LOOP; 
END $$;

Run backend tests:

```powershell
pytest backend/tests
```

Or from `backend`:

```powershell
cd backend
pytest
```

### Run a specific test

```powershell
pytest backend/tests/test_something.py
```

### Run with more detail

```powershell
pytest backend/tests -v
```

---

## 7. 🚀 Run FastAPI locally

If you're developing without Docker:

```powershell
cd backend
uvicorn app.main:app --reload
```

Then:

```
http://localhost:8000/docs
```

But once we're using Docker as the deployment environment, you'll increasingly use:

```powershell
docker compose up
```

instead.

---

## 8. 🧪 Frontend tests

From the project root:

```powershell
npm test
```

Install dependencies if needed:

```powershell
npm install
```

The cleaner CI-style install is:

```powershell
npm ci
```

---

## 9. 📦 Git commands

### Check what's changed

```powershell
git status
```

You'll use this **all the time**.

### See changes

```powershell
git diff
```

### Stage changes

Everything:

```powershell
git add .
```

Specific file:

```powershell
git add backend/Dockerfile
```

### Commit

```powershell
git commit -m "your message"
```

### Push

```powershell
git push
```

### Pull latest changes

```powershell
git pull
```

### See recent commits

```powershell
git log --oneline -10
```

---

## 10. 🔍 Inspect Docker images

### List images

```powershell
docker images
```

### See containers, including stopped ones

```powershell
docker ps -a
```

### See Docker volumes

```powershell
docker volume ls
```

Your database volume should look something like:

```
hpqms-project_hpqms_postgres_data
```

---

## 11. 🧹 Docker cleanup

### Remove stopped containers

```powershell
docker container prune
```

### Remove unused images

```powershell
docker image prune
```

### See Docker disk usage

```powershell
docker system df
```

Don't routinely use:

```powershell
docker system prune -a
```

unless you understand what you're removing. It can delete a lot of cached Docker resources.

---

## ⭐ The commands I'd memorize first

You really don't need to memorize everything above.

For your current HPQMS phase, I'd put these **12 commands** somewhere easy to access:

```powershell
# Start
docker compose up -d

# Rebuild + start
docker compose up -d --build

# Check containers
docker compose ps

# Watch logs
docker compose logs -f

# Backend logs
docker compose logs -f backend

# Stop
docker compose down

# Fresh database
docker compose down -v

# Database tables
docker exec hpqms-postgres psql -U hpqms -d hpqms -c "\dt"

# Seed
docker exec hpqms-backend python seed.py

# Backend tests
pytest backend/tests

# Git status
git status

# Push
git add .
git commit -m "message"
git push
```

---

## Your normal HPQMS testing cycle

Once Docker is fully set up, your day-to-day workflow will often look like:

```
1. Make code changes
        ↓
2. Run tests
        ↓
3. Build/start Docker
        ↓
4. Check logs
        ↓
5. Test application in browser
        ↓
6. Check database if necessary
        ↓
7. git status
        ↓
8. git add / commit / push
```

And when you want to start a **completely clean test session**:

```powershell
docker compose down -v
docker compose up -d --build
docker exec hpqms-backend python seed.py
docker compose ps
```

That's probably the most useful little HPQMS Docker routine to keep handy.
