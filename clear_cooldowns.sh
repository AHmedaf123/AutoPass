#!/bin/bash
# Clear Database Cooldowns - Using PSQL

# Database credentials from .env
DB_HOST="localhost"
DB_PORT="5433"
DB_NAME="jobapplier"
DB_USER="postgres"
DB_PASS="itechgemini"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         Clear Database Cooldowns - Test Severity Fix           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

# Export password for psql
export PGPASSWORD="$DB_PASS"

echo "🔄 Checking current cooldowns..."
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME << EOF
SELECT 
  email,
  cooldown_until,
  last_session_outcome,
  EXTRACT(EPOCH FROM (cooldown_until - NOW())) / 3600 as hours_remaining
FROM users
WHERE cooldown_until IS NOT NULL AND cooldown_until > NOW()
ORDER BY cooldown_until DESC;
EOF

echo
echo "🧹 Clearing all cooldowns..."
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME << EOF
UPDATE users
SET cooldown_until = NULL, last_session_outcome = NULL
WHERE cooldown_until IS NOT NULL;
EOF

echo
echo "✅ Verifying..."
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME << EOF
SELECT COUNT(*) as users_with_active_cooldowns
FROM users
WHERE cooldown_until IS NOT NULL AND cooldown_until > NOW();
EOF

echo
echo "✅ Done!"
