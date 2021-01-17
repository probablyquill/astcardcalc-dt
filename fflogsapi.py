"""
This contains code for pull requests from v2 of the FFLogs API
as required for damage and card calculations used in cardcalc
and damagecalc
"""

from datetime import timedelta
import os

# local imports
from cardcalc_data import Player, Pet, FightInfo

# Imports related to making API requests
import requests
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient
from python_graphql_client import GraphqlClient

FFLOGS_CLIENT_ID = os.environ['FFLOGS_CLIENT_ID']
FFLOGS_CLIENT_SECRET = os.environ['FFLOGS_CLIENT_SECRET']

FFLOGS_OAUTH_URL = 'https://www.fflogs.com/oauth/token'
FFLOGS_URL = 'https://www.fflogs.com/api/v2/client'

client = GraphqlClient(FFLOGS_URL)

# this is used to handle sorting events
def event_priority(event):
    return {
        'applydebuff': 1,
        'applybuff': 1,
        'refreshdebuff': 2,
        'refreshbuff': 2,
        'removedebuff': 4,
        'removebuff': 4,
        'damage': 3,
        'damagesnapshot': 3,
    }[event]

# used to obtain a bearer token from the fflogs api
def get_bearer_token():
    token_client = BackendApplicationClient(client_id=FFLOGS_CLIENT_ID)
    oauth = OAuth2Session(client=token_client)
    token = oauth.fetch_token(token_url=FFLOGS_OAUTH_URL, client_id=FFLOGS_CLIENT_ID, client_secret=FFLOGS_CLIENT_SECRET)
    return token

    headers = {
        'Content-TYpe': 'application/json',
        'Authorization': 'Bearer {}'.format(token['access_token']),
    }
    response = requests.request('POST', FFLOGS_URL, data=payload, headers=headers)

    return response

# make a request for the data defined in query given a set of
# variables
def call_fflogs_api(query, variables, token):
    headers = {
        'Content-TYpe': 'application/json',
        'Authorization': 'Bearer {}'.format(token['access_token']),
    }
    data = client.execute(query=query, variables=variables, headers=headers)

    return data

def get_fight_info(report, fight, token):
    variables = {
        'code': report
    }
    query = """
query reportData($code: String!) {
    reportData {
        report(code: $code) {
            fights {
                id
                startTime
                endTime
            }
        }
    }
}
"""
    data = call_fflogs_api(query, variables, token)
    fights = data['data']['reportData']['report']['fights']

    for f in fights:
        if f['id'] == fight:
            return FightInfo(report_id=report, fight_number=fight, start_time=f['startTime'], end_time=f['endTime'])

def get_actor_lists(fight_info: FightInfo, token):
    variables = {
        'code': fight_info.id,
        'startTime': fight_info.start,
        'endTime': fight_info.end,
    }
    
    query = """
query reportData($code: String!, $startTime: Float!, $endTime: Float) {
    reportData {
        report(code: $code) {
            masterData {
                pets: actors(type: "Pet") {
                    id
                    name
                    type
                    subType
                    petOwner
                }
            }
            table: table(startTime: $startTime, endTime: $endTime)
        }
    }
}"""

    data = call_fflogs_api(query, variables, token)
    master_data = data['data']['reportData']['report']['masterData']
    table = data['data']['reportData']['report']['table']

    pet_list = master_data['pets']
    composition = table['data']['composition']

    players = {}
    pets = {}

    for p in composition:
        players[p['id']] = Player(p['id'], p['name'], p['type'])

    for p in pet_list:
        if p['petOwner'] in players:
            pets[p['id']] = Pet(p['id'], p['name'], p['petOwner'])

    return (players, pets)

def get_card_play_events(fight_info: FightInfo, token):
    variables = {
        'code': fight_info.id,
        'startTime': fight_info.start,
        'endTime': fight_info.end,
    }
    query = """
query reportData($code: String!, $startTime: Float!, $endTime: Float!) {
    reportData {
        report(code: $code) {
            cards: events(
                startTime: $startTime, 
                endTime: $endTime
                dataType: Buffs,
                filterExpression: "ability.id in (1001877, 1001883, 1001886, 1001887, 1001876, 1001882, 1001884, 1001885)"
            ) {
                data
            }
        }
    }
}
"""

    data = call_fflogs_api(query, variables, token)
    card_events = data['data']['reportData']['report']['cards']['data']
    
    return card_events

def get_card_draw_events(fight_info: FightInfo, token):
    variables = {
        'code': fight_info.id,
        'startTime': fight_info.start,
        'endTime': fight_info.end,
    }
    query = """
query reportData($code: String!, $startTime: Float!, $endTime: Float!) {
    reportData {
        report(code: $code) {
            draws: events(
                startTime: $startTime,
                endTime: $endTime,
                filterExpression: "ability.id in (3590, 7448, 3593, 1000915, 1000913, 1000914, 1000917, 1000916, 1000918)"
                ) {
                    data
                }
        }
    }
}
"""

    data = call_fflogs_api(query, variables, token)
    card_events = data['data']['reportData']['report']['draws']['data']
    
    return card_events

# this shouldn't be used much but can be useful so I'm leaving it in
def get_damages(fight_info: FightInfo, token):
    variables = {
        'code': fight_info.id,
        'startTime': fight_info.start,
        'endTime': fight_info.end,
    }
    query = """
query reportData ($code: String!, $startTime: Float!, $endTime: Float!) {
    reportData {
        report(code: $code) {
            table(
                startTime: $startTime, 
                endTime: $endTime,
                dataType: DamageDone,
                filterExpression: "isTick='false'",
                viewBy: Source
                )
        }
    }
}"""
    
    data = call_fflogs_api(query, variables, token)
    damage_entries = data['data']['reportData']['report']['table']['data']['entries']

    damages = {}

    for d in damage_entries:
        damages[d['id']] = d['total']

    return damages

def get_damage_events(fight_info: FightInfo, token):
    variables = {
        'code': fight_info.id,
        'startTime': fight_info.start,
        'endTime': fight_info.end,
    }
    query = """
query reportData($code: String!, $startTime: Float!, $endTime: Float!) {
    reportData {
        report(code: $code) {
            damage: events(
                startTime: $startTime,
                endTime: $endTime,
                dataType: DamageDone,
                limit: 10000,
                filterExpression: "isTick='false' and type!='calculateddamage'"
            ) {
                data
            }
            tickDamage: events(
                startTime: $startTime,
                endTime: $endTime,
                dataType: DamageDone,
                limit: 10000,
                filterExpression: "isTick='true' and ability.id != 500000"
            ) {
                data
            }
            tickEvents: events(
                startTime: $startTime,
                endTime: $endTime,
                dataType: Debuffs,
                hostilityType: Enemies,
                limit: 10000,
                filterExpression: "ability.id not in (1000493, 1001203, 1001195, 1001221)"
            ) {
                data
            }
            groundEvents: events(
                startTime: $startTime,
                endTime: $endTime,
                dataType: Buffs,
                limit: 10000,
                filterExpression: "ability.id in (1000749, 1000501, 1001205, 1000312, 1001869)"
            ) {
                data
            }
        }
    }
}
"""

    data = call_fflogs_api(query, variables, token)

    base_damages = data['data']['reportData']['report']['damage']['data']
    tick_damages = data['data']['reportData']['report']['tickDamage']    ['data']
    tick_events = data['data']['reportData']['report']['tickEvents']['data']
    ground_events = data['data']['reportData']['report']['groundEvents']['data']

    combined_tick_events = sorted((tick_damages + tick_events + ground_events), key=lambda tick: (tick['timestamp'], event_priority(tick['type'])))

    damage_events = {
        'rawDamage': base_damages,
        'tickDamage': combined_tick_events,
    }
    return damage_events
