.PHONY: sync build up down restart deploy logs logs-gateway logs-ai status

sync:
	python deploy.py sync

build:
	python deploy.py build

up:
	python deploy.py up

down:
	python deploy.py down

restart:
	python deploy.py restart

deploy:
	python deploy.py deploy

logs:
	python deploy.py logs

logs-gateway:
	python deploy.py logs-gateway

logs-ai:
	python deploy.py logs-ai

status:
	python deploy.py status
