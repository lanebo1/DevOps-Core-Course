# DevOps Info Service (FastAPI)

## Overview

A small web service that reports service metadata, system details, runtime uptime, and request information. Built as the foundation for future DevOps labs.

## Prerequisites

- Python 3.11+

## Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the Application

```bash
python3 app.py
```

API Endpoints

- `GET /` - Service and system information
- `GET /health` - Health check

## Configuration

| Variable  | Default     | Description         |
| --------- | ----------- | ------------------- |
| `HOST`  | `0.0.0.0` | Bind address        |
| `PORT`  | `5000`    | Server port         |
| `DEBUG` | `False`   | Enables auto-reload |
