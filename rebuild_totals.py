import os, json
from collections import OrderedDict
import psycopg2

from main import track_targets

PG_USER = os.environ['PG_USER']
PG_PW = os.environ['PG_PASSWORD']

PG_SERVER = "50.116.36.193"
# PG_SERVER = "127.0.0.1"
PG_DB = "cardcalc"
PG_PORT = "5432"

client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
cur = client.cursor()

sql = """SELECT * FROM reports"""
cur.execute(sql)
reports = cur.fetchall()

# Create backup in case interrupted or data is otherwise mangled.
sql = """DROP TABLE IF EXISTS targetsbu;"""
cur.execute(sql)

sql = """CREATE TABLE targetsbu AS TABLE targets;"""
cur.execute(sql)

sql = """TRUNCATE TABLE targets;"""
cur.execute(sql)

client.commit()
client.close()

# Unforutnately there's some issues that I need to fix on the reports tracking side. This will prevent duplicates in the interim.
calculated_reports = []

for r in reports:
    report_id, fight_id, results, actors, enc_name, enc_time, enc_kill, computed, difficulty = r

    #if enc_name.lower() == "doomtrain": continue
    if (report_id, fight_id) in calculated_reports: continue
    report = {
            'report_id': report_id,
            'fight_id': fight_id,
            'results': json.loads(results),
            'actors': json.loads(actors),
            'enc_name': enc_name,
            'enc_time': enc_time,
            'enc_kill': enc_kill,
            'computed': computed,
            'difficulty': difficulty,
        }
    print(f"Adding {enc_name} : {report_id}/{fight_id} to targets.")
    
    # Cleanup results data so that it appears as expected to the track_targets function.
    report['results'] = list(OrderedDict(
        sorted(report['results'].items())).values())
    
    track_targets(report)
    calculated_reports.append((report_id, fight_id))


# NOTE: MODIFY PROD TABLE
# ALTER TABLE reports ADD COLUMN difficulty INT DEFAULT 100;