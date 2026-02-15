@echo off
REM Clear Database Cooldowns - For Testing
REM Windows batch script to clear user cooldowns from PostgreSQL database

setlocal enabledelayedexpansion

set DB_HOST=localhost
set DB_PORT=5433
set DB_NAME=jobapplier
set DB_USER=postgres
set DB_PASS=itechgemini

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║         Clear Database Cooldowns - Test Severity Fix           ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

set PGPASSWORD=%DB_PASS%

echo 📊 Current cooldowns in database:
echo.
psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "SELECT email, cooldown_until, last_session_outcome, EXTRACT(EPOCH FROM (cooldown_until - NOW())) / 3600 as hours_remaining FROM users WHERE cooldown_until IS NOT NULL AND cooldown_until > NOW() ORDER BY cooldown_until DESC;"

echo.
echo 🧹 Clearing all cooldowns...
echo.
psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "UPDATE users SET cooldown_until = NULL, last_session_outcome = NULL WHERE cooldown_until IS NOT NULL; SELECT 'Updated: ' || COUNT(*) FROM users WHERE cooldown_until IS NULL;"

echo.
echo ✅ Verification - cooldowns still active:
echo.
psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "SELECT COUNT(*) as active_cooldowns FROM users WHERE cooldown_until IS NOT NULL AND cooldown_until > NOW();"

echo.
echo ✅ Done! Database ready for testing.
echo.

set PGPASSWORD=
endlocal
