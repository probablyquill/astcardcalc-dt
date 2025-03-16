from datetime import datetime
import pytz
import os
import json
from collections import OrderedDict
from urllib.parse import urlparse, parse_qs
import psycopg2

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

    return render_template('calc.html', report=report)