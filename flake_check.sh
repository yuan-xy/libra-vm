#!/bin/bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --exclude=test,tests --count --select=F841 --show-source --statistics
