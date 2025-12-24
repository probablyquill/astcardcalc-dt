#!/bin/bash
gunicorn -b localhost:8080 -w 1 main:app
