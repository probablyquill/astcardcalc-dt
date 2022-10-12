from datetime import datetime
import os
from urllib.parse import urlparse, parse_qs

from flask import Flask, render_template, request, redirect, send_from_directory, url_for

from cardcalc_fflogsapi import decompose_url, get_bearer_token
from cardcalc_data import  CardCalcException
from cardcalc_cards import cardcalc

app = Flask(__name__)

LAST_CALC_DATE = datetime.fromtimestamp(1663886556)

token = get_bearer_token()

def increment_count(db):
    count = Count.query.get(1)

    count.total_reports = count.total_reports + 1
    db.session.commit()

def prune_reports(db):
    if Report.query.count() > 9500:
        # Get the computed time of the 500th report
        delete_before = Report.query.order_by('computed').offset(500).first().computed

        # Delete reports before that
        Report.query.filter(Report.computed < delete_before).delete()
        db.session.commit()

@app.route('/', methods=['GET', 'POST'])
def homepage():
    """Simple form for redirecting to a report, no validation"""
    if request.method == 'POST':
        report_url = request.form['report_url']
        try:
            report_id, fight_id = decompose_url(report_url, token)
        except CardCalcException as exception:
            return render_template('error.html', exception=exception)

        return redirect(url_for('calc', report_id=report_id, fight_id=fight_id))

    return render_template('home.html')

@app.route('/about')
def about():
    # TODO: Fix this
    try:
        count = Count.query.get(1)
    except:
        print('Count db error.')
        # db.create_all()
        # db.session.add(count)
        # db.session.commit()
        count = Count(count_id = 1, total_reports = 1)
    # value pre-full database reset
    prev_report_count = 14140
    total_count = count.total_reports + prev_report_count
    return render_template('about.html', report_count=total_count)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/png')

@app.route('/<string:report_id>/<int:fight_id>')
def calc(report_id, fight_id):
    """The actual calculated results view"""
    # Very light validation, more for the db query than for the user
    if ( len(report_id) < 14 or len(report_id) > 22 ):
        return redirect(url_for('homepage'))

    # TODO: Fix this
    try:
        report = Report.query.filter_by(report_id=report_id, fight_id=fight_id).first()
    except:
        print('Report db error')
        print(os.path.dirname(os.path.realpath(__file__)))        
        db.create_all()
        report = Report.query.filter_by(report_id=report_id, fight_id=fight_id).first()

    if report:
        # Recompute if no computed timestamp
        if not report.computed or report.computed < LAST_CALC_DATE:
            try:
                results, actors, encounter_info = cardcalc(report_id, fight_id, token)
            except CardCalcException as exception:
                return render_template('error.html', exception=exception)

            report.results = results
            report.actors = actors
            report.enc_name = encounter_info['enc_name']
            report.enc_time = encounter_info['enc_time']
            report.enc_kill = encounter_info['enc_kill']
            report.computed = datetime.now()

            db.session.commit()

        # TODO: this is gonna cause some issues
        # These get returned with string keys, so have to massage it some
        actors = {int(k):v for k,v in report.actors.items()}

    else:
        try:
            results, actors, encounter_info = cardcalc(report_id, fight_id, token)
        except CardCalcException as exception:
            return render_template('error.html', exception=exception)

        report = Report(
            report_id=report_id,
            fight_id=fight_id,
            results=results,
            actors=actors,
            **encounter_info
            )
        try:
            # Add the report
            db.session.add(report)
            db.session.commit()

            # Increment count
            increment_count(db)

            # Make sure we're not over limit
            prune_reports(db)

        except IntegrityError as exception:
            # This was likely added while cardcalc was running,
            # in which case we don't need to do anything besides redirect
            pass

    return render_template('calc.html', report=report, actors=actors)