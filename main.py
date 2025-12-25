from datetime import datetime
import pytz
import os
import json
from collections import OrderedDict
from urllib.parse import urlparse, parse_qs
import psycopg2
import psycopg2.extras

from flask import Flask, render_template, request, \
    redirect, send_from_directory, url_for

from cardcalc_fflogsapi import decompose_url, get_bearer_token
from cardcalc_data import CardCalcException
from cardcalc_cards import cardcalc

PG_USER = os.environ['PG_USER']
PG_PW = os.environ['PG_PASSWORD']

PG_SERVER = "127.0.0.1"
PG_DB = "cardcalc"
PG_PORT = "5432"

app = Flask(__name__)
LAST_CALC_DATE = pytz.UTC.localize(datetime.utcfromtimestamp(1663886556))
token = get_bearer_token()

client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
cur = client.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS reports(report_id TEXT, fight_id INT, results TEXT, actors TEXT, enc_name TEXT, enc_time TIME, enc_kill BOOLEAN, computed TEXT);")
cur.execute("CREATE TABLE IF NOT EXISTS counts(total_reports INT);")
cur.execute("CREATE TABLE IF NOT EXISTS targets(job TEXT, cardId INT, encounterId TEXT, difficulty INT, average BIGINT, max BIGINT, total INT);")

#Check on the report total counting / establish the counter if doesn't exist:
count = cur.execute("SELECT * FROM counts;")
count = cur.fetchone()
if count == None:
    cur.execute("INSERT INTO counts(total_reports) values(0);")

client.commit()
client.close()

def get_count():
    client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
    cur = client.cursor()
    cur.execute("SELECT * FROM counts;")

    count_query = cur.fetchone()[0]
    client.close()

    return count_query

def increment_count():
    count = get_count()
    report_count = count + 1

    sql = """
UPDATE counts
SET total_reports = %s
WHERE total_reports = %s;
"""

    client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
    cur = client.cursor()
    cur.execute(sql, (report_count, count))

    client.commit()
    client.close()

    return report_count

def prune_reports():
    pass

def prune_reports_old():
    client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
    cur = client.cursor()

    Reports = cur.execute("SELECT COUNT(*) FROM Reports;")
    
    if Reports > 10000:
        sql_get = """SELECT computed FROM `Reports`
    ORDER BY computed ASC
    LIMIT 1 OFFSET 500;"""
        time_query = client.query(sql_get).result()
        computed_cutoff = next(time_query).get('computed')
        sql_delete = """DELETE FROM `astcardcalc-vm.Reports.Reports`
WHERE computed < {};""".format(computed_cutoff)
        client.query(sql_delete).result()
    
    client.commit()
    client.close()

def track_targets(report):
    print(report)
    client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
    cur = client.cursor()

    encounter_id = report['enc_name']
    difficulty = report['difficulty']
    if report['enc_kill'] == True and difficulty != None:

        sql = "SELECT cardId, job, average, max, total FROM targets WHERE encounterId=%s AND difficulty=%s"
        cur.execute(sql, (encounter_id, difficulty))
        job_data = cur.fetchall()

        cleaned_data = {}

        for j in job_data:
            card, job_name, average, max, total = j
            cleaned_data[(job_name, card)] = [average, max, total]

        # Loop through the all jobs present on each play window and save their adjusted damage to the database.
        for window in report['results']:
            if 'cardId' not in window: continue
            card = window['cardId']
            for row in window['cardDamageTable']:
                job = row['job'].lower()
                damage = row['adjustedDamage']

                if ((job, card) in cleaned_data):
                    job_result = cleaned_data[(job, card)]
                else:
                    job_result = None
                # sql = "SELECT average, max, total FROM targets WHERE job=%s AND cardId=%s AND encounterId=%s AND difficulty=%s;"
                # cur.execute(sql, (job, card, encounter_id, difficulty))
                # job_result = cur.fetchone()

                if (job_result == None):
                    # sql = "INSERT INTO targets(job, cardId, encounterId, difficulty, average, max, total) VALUES (%s, %s, %s, %s, %s, %s, %s);"
                    # cur.execute(sql, (job, card, encounter_id, difficulty, damage, damage, 1))
                    cleaned_data[(job, card)] = [damage, damage, 1]
                else:
                    db_avg, db_max, total = job_result
                    # My understanding is that Python Longs don't overflow so theoretically this is fine forever even if naive(?)
                    new_avg = ((db_avg * total) + damage) / (total + 1)
                    total+=1 
                    if (db_max < damage): db_max = damage

                    cleaned_data[(job, card)] = [new_avg, db_max, total]

                    # Cannot use REPLACE because there is no Unique or Primary key, it may best to restructure the DB but for now this gets to the exact functionality I need.
                    # sql = "DELETE FROM targets WHERE job=%s AND cardId=%s AND encounterId=%s AND difficulty = %s"
                    # cur.execute(sql, (job, card, encounter_id, difficulty))

                    # sql = "INSERT INTO targets(job, cardId, encounterId, difficulty, average, max, total) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    # cur.execute(sql, (job, card, encounter_id, difficulty, new_avg, db_max, total))
        
        # Changed to batch all insert / delete records together to make it not take 5 seconds because of networking.
        
        sql = "DELETE FROM targets WHERE encounterId=%s AND difficulty=%s"
        cur.execute(sql, (encounter_id, difficulty))

        sql_data = []
        for job, card in cleaned_data:
            avg, max, total = cleaned_data[(job, card)]
            sql_data.append(
                (job, card, encounter_id, difficulty, avg, max, total)
            )

        sql = "INSERT INTO targets(job, cardId, encounterId, difficulty, average, max, total) VALUES %s"
        psycopg2.extras.execute_values(cur, sql, sql_data)

    client.commit()
    client.close()

@app.route('/', methods=['GET', 'POST'])
def homepage():
    """Simple form for redirecting to a report, no validation"""
    if request.method == 'POST':
        report_url = request.form['report_url']
        try:
            report_id, fight_id = decompose_url(report_url, token)
        except CardCalcException as exception:
            return render_template('error.html', exception=exception)

        return redirect(url_for('calc',
                                report_id=report_id,
                                fight_id=fight_id))

    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html', report_count=get_count())


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/png')


@app.route('/<string:report_id>/<int:fight_id>')
def calc(report_id, fight_id):
    client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
    cur = client.cursor()

    """The actual calculated results view"""
    # Very light validation, more for the db query than for the user
    if (len(report_id) < 14 or len(report_id) > 24):
        return redirect(url_for('homepage'))

    sql_report = None
    report = None

    sql = """SELECT * FROM reports WHERE report_id=%s AND fight_id=%s ORDER BY computed DESC;"""
    query_res = cur.execute(sql, (str(report_id), fight_id))

    if (query_res != None):
        query_res.fetchone()

        report = {
            'report_id': query_res[0],
            'fight_id': query_res[1],
            'results': json.loads(query_res[2]),
            'actors': json.loads(query_res[3]),
            'enc_name': query_res[4],
            'enc_time': query_res[5],
            'enc_kill': query_res[6],
            'computed': query_res[7],
        }

    if sql_report is None:
        # Compute
        try:
            results, actors, encounter_info = cardcalc(
                report_id, fight_id, token)
        except CardCalcException as exception:
            return render_template('error.html', exception=exception)

        sql_report = {
            'report_id': report_id,
            'fight_id': fight_id,
            'results': json.dumps(results),
            'actors': json.dumps(actors),
            'enc_name': encounter_info['enc_name'],
            'enc_time': encounter_info['enc_time'],
            'enc_kill': encounter_info['enc_kill'],
            'computed': datetime.now().isoformat(),
            'difficulty': encounter_info['difficulty'],
        }
        report = {
            'report_id': report_id,
            'fight_id': fight_id,
            'results': results,
            'actors': actors,
            'enc_name': encounter_info['enc_name'],
            'enc_time': encounter_info['enc_time'],
            'enc_kill': encounter_info['enc_kill'],
            'computed': datetime.now(),
            'difficulty': encounter_info['difficulty'],
        }

        # print(sql_report)
        sql = """INSERT INTO
            reports(report_id, fight_id, results, actors, enc_name, enc_time, enc_kill, computed) 
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s);
            """
        row_result = cur.execute(sql, (sql_report['report_id'], sql_report['fight_id'], sql_report['results'], 
                                sql_report['actors'], sql_report['enc_name'], sql_report['enc_time'], sql_report['enc_kill'], sql_report['computed']))
        # print(row_result)

        client.commit()
        client.close()

        increment_count()

    else:
        # print(sql_report['computed'])
        # print(type(sql_report['computed']))
        # print(LAST_CALC_DATE)
        # print(type(LAST_CALC_DATE))

        # Recompute if no computed timestamp
        if sql_report['computed'] < LAST_CALC_DATE:
            try:
                results, actors, encounter_info = cardcalc(
                    report_id, fight_id, token)
            except CardCalcException as exception:
                return render_template('error.html', exception=exception)

            sql_report = {
                'report_id': report_id,
                'fight_id': fight_id,
                'results': json.dumps(results),
                'actors': json.dumps(actors),
                'enc_name': encounter_info['enc_name'],
                'enc_time': encounter_info['enc_time'],
                'enc_kill': encounter_info['enc_kill'],
                'computed': datetime.now().isoformat(),
                'difficulty': encounter_info['difficulty'],
            }
            report = {
                'report_id': report_id,
                'fight_id': fight_id,
                'results': results,
                'actors': actors,
                'enc_name': encounter_info['enc_name'],
                'enc_time': encounter_info['enc_time'],
                'enc_kill': encounter_info['enc_kill'],
                'computed': datetime.now(),
                'difficulty': encounter_info['difficulty'],
            }
            sql = """INSERT OR REPLACE INTO
            reports(report_id, fight_id, results, actors, enc_name, enc_time, enc_kill, computed) 
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s);"""
            
            sql.replace("'", "\'")
            sql.replace('\"', "\"")
            row_result = cur.execute(sql, (sql_report['report_id'], sql_report['fight_id'], sql_report['results'], 
                                           sql_report['actors'], sql_report['enc_name'], sql_report['enc_kill'], sql_report['computed']))

            client.commit()
            client.close()

    report['results'] = {int(k): v for k, v in report['results'].items()}
    report['actors'] = {int(k): v for k, v in report['actors'].items()}

    report['results'] = list(OrderedDict(
        sorted(report['results'].items())).values())
    actors = {int(k): v for k, v in report['actors'].items()}
    #TODO Clean up DB access and reduce the number of times the connection is opened and closed.

    #Track best targets to compile in database
    track_targets(report)
    
    return render_template('calc.html', report=report)

@app.route('/encounter/<string:encounter>/')
def encounter_report(encounter):
    print(encounter)
    client = psycopg2.connect(database=PG_DB, host=PG_SERVER, user=PG_USER, password=PG_PW, port=PG_PORT)
    cur = client.cursor()

    sql = """SELECT DISTINCT encounterid FROM targets;"""
    cur.execute(sql)
    encounters = cur.fetchall()

    cleaned_encounters = []
    for e in encounters:
        cleaned_encounters.append((e[0]))
    
    # This is not my favorite way to do this but it does work and is very concise.
    lower_list = [e.lower().replace(" ", "") for e in cleaned_encounters]

    try:
        index = lower_list.index(encounter.lower())
    except ValueError:
        return render_template('error.html', exception="Database Error: Encounter not found.")

    # The point of this segment is to correctly pull capitalization / punctuation from the DB's encounterid.
    encounter = cleaned_encounters[index]
    
    sql = """SELECT job, cardid, difficulty, average, max, total FROM targets WHERE encounterid=%s ORDER BY average DESC"""
    cur.execute(sql, (encounter,))
    encounter_data = cur.fetchall()

    ranged_list = []    # 37023 = The Balance
    melee_list = []     # 37026 = The Spear

    savage_present = False
    # Since everything is arriving pre-sorted by the database, we'll just split it by card types as is.
    for item in encounter_data:
        # We will need difficulty later for distinguishing between normal and savage. It does not matter for ex.
        job, card, difficulty, average, max, total = item

        # Smile
        job = job[0].upper() + job[1:]
        if difficulty == 101: savage_present = True
        if difficulty == 100 and savage_present == True: continue

        if card == 37023:
            melee_list.append((job, average, max, total))
        elif card == 37026:
            ranged_list.append((job, average, max, total))

    # TODO this 'works' but is a temporary solution until I find one I like better.
    if savage_present:
        new_ranged = []
        new_melee = []
        for item in ranged_list:
            job, card, difficulty, *discard = item
            if difficulty == 101: new_ranged.add(item)
        for item in melee_list:
            job, card, difficulty, *discard = item
            if difficulty == 101: new_melee.add(item)
        ranged_list = new_ranged
        melee_list = new_melee

    ranged_list = ranged_list[:8]
    melee_list = melee_list[:8]
    return render_template('encounter.html', ranged_list=ranged_list, melee_list=melee_list, encounter=encounter)
    # return render_template('encounter.html', data=data)