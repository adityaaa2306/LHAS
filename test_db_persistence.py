import psycopg2
import json

conn = psycopg2.connect(
    host='localhost',
    database='lhas',
    user='user',
    password='password',
    port='5432'
)

cur = conn.cursor()

# First check if query_analysis table exists
cur.execute("""
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'query_analysis'
);
""")
table_exists = cur.fetchone()[0]
print(f'query_analysis table exists: {table_exists}')

if table_exists:
    # Check records for mission
    cur.execute("""
    SELECT id, mission_id, original_query, intent_type, confidence_score, decision, created_at
    FROM query_analysis 
    WHERE mission_id = '6321aa5f-8832-4055-9968-2f3ffb8194f7'
    ORDER BY created_at DESC
    LIMIT 1
    """)
    
    result = cur.fetchone()
    if result:
        print(f'\nQuery analysis record FOUND:')
        print(f'  ID: {result[0]}')
        print(f'  Mission ID: {result[1]}')
        print(f'  Original Query: {result[2]}')
        print(f'  Intent Type: {result[3]}')
        print(f'  Confidence Score: {result[4]}')
        print(f'  Decision: {result[5]}')
        print(f'  Created At: {result[6]}')
    else:
        print('\nNo query analysis record found for this mission ID')
        print('Checking all records in query_analysis table:')
        cur.execute('SELECT COUNT(*) FROM query_analysis')
        count = cur.fetchone()[0]
        print(f'Total records in query_analysis: {count}')
        
        if count > 0:
            print('\nAll records:')
            cur.execute("SELECT id, mission_id, original_query, intent_type, confidence_score FROM query_analysis LIMIT 5")
            for row in cur.fetchall():
                print(f'  - Mission {row[1]}: {row[2][:50]}... (type: {row[3]}, confidence: {row[4]})')
else:
    print('query_analysis table does not exist!')
    # Show all tables
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = cur.fetchall()
    print('\nAvailable tables:')
    for t in tables:
        print(f'  - {t[0]}')

conn.close()
