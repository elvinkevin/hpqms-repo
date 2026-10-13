import asyncio
import asyncpg

from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL.replace("+asyncpg", "", 1)

async def main():
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # ============================================================
        # DATABASE INFORMATION
        # ============================================================

        result = await conn.fetchrow(
            """
            SELECT
                current_database() AS database_name,
                current_user AS database_user,
                version() AS postgres_version
            """
        )

        print("=" * 60)
        print("HPQMS LIVE DATABASE CHECK")
        print("=" * 60)

        print("Database:", result["database_name"])
        print("User:", result["database_user"])
        print("PostgreSQL:", result["postgres_version"])

        # ============================================================
        # TABLES
        # ============================================================

        tables = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )

        print("\nTables:")
        for table in tables:
            print(f"  - {table['table_name']}")

        # ============================================================
        # RECORD COUNTS
        # ============================================================

        print("\nRecord counts:")

        expected_tables = [
            "staff",
            "departments",
            "patients",
            "visits",
            "queue_entries",
        ]

        existing_tables = {
            table["table_name"]
            for table in tables
        }

        for table_name in expected_tables:
            if table_name in existing_tables:
                result = await conn.fetchrow(
                    f"SELECT COUNT(*) AS count FROM {table_name}"
                )

                print(
                    f"  {table_name:<20} {result['count']}"
                )
            else:
                print(
                    f"  {table_name:<20} TABLE NOT FOUND"
                )

        # ============================================================
        # ACTIVE QUEUE
        # ============================================================

        if "queue_entries" in existing_tables:

            print("\nQueue entries:")

            queue_entries = await conn.fetch(
                """
                SELECT
                    queue_entry_id,
                    status,
                    priority,
                    dept_id,
                    visit_id
                FROM queue_entries
                ORDER BY entered_at
                """
            )

            if not queue_entries:
                print("  No queue entries found.")

            else:
                for entry in queue_entries:
                    print(
                        f"  {entry['queue_entry_id']} | "
                        f"status={entry['status']} | "
                        f"priority={entry['priority']} | "
                        f"department={entry['dept_id']} | "
                        f"visit={entry['visit_id']}"
                    )

        print("\n" + "=" * 60)
        print("DATABASE CHECK COMPLETE")
        print("=" * 60)

    finally:
        await conn.close()


asyncio.run(main())