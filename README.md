# Astrologian Card Calulator
## About

This is a tool for analyzing FFLogs to determine optimal Astrologian card usage. You can use this application [here](http://calc.probablyquill.com), or follow the instructions below to download and run it locally. 

## Installation

Install the dependencies:
```sh
pip install -r requirements.txt
```

By default, the application is useing gunicorn as its WSGI. Gunicorn only runs on UNIX systems. 
If you want to run the program on Windows, you can use waitress with minimal modifications.

To use the program, you will need both an FFLogs auth ID and a secret key. Instructions for obtaining those can be found [here](https://www.fflogs.com/api/docs).

The program expects the ID and secret to be stored in environment variables FFLOGS_CLIENT_ID and FFLOGS_CLIENT_SECRET.
It also expects a postgres username and password to be specified in PG_USER and PG_PASSWORD.

Should you prefer to forgo using environmental variables, the values can be hardcoded in [cardcalc_fflogsapi.py](cardcalc_fflogsapi.py) for the fflogs keys and [main.py](main.py) for the postgres settings.

After the id, secret, and postgres credentials are configured, the program can be executed by executing the [run.sh](run.sh) file. You will need to have any firewalls or port mapping configured appropriately for the program to be reachable externally.


## Usage
The gunicorn execution command in run.sh is structured as follows:

```sh
gunicorn -b [IP ADDRESS]:[PORT] -w [NUMBER OF WORKERS] main:app
```

## Credits
This is a fork of [meldontaragon's](https://github.com/meldontaragon) [astcardcalc](https://github.com/meldontaragon/astcardcalc) project.

Tooltips and icons are provided thanks to the [Vue-XIVTooltips](https://github.com/xivapi/vue-xivtooltips) library.

If there are any issues with the website or the project, please DM me on discord @probablyquill or submit an issue on GitHub.