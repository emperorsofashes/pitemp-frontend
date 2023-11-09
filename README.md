# Price History
A simple Flask application to display price history.

## Prerequisites
You will need a [MongoDB](https://www.mongodb.com/) database to run this application.
You can get a free MongoDB database by signing up for [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
MongoDB Atlas has a free tier which includes a simple cluster deployment.

This README assumes you are running on Linux.

You will need a [Python 3](https://www.python.org/about/) interpreter to run this application.
The Python 3 interpreter should include the `venv` module.

## Setup

### Python
You will need to create a virtual environment to run this application.
Run the following commands at the root of this repo:
```
python3 -m venv venv
source venv/bin/activate
pip install -Ur requirements.txt
```

### SSL
To preserve consistency with running in the cloud, this application uses HTTPS even when running locally.
You will need to run the following commands from the root of the repo to get ready for HTTPS:
```
mkdir ssl
cd ssl
openssl req -nodes -new -x509 -keyout server.key -out server.crt \
    -subj "/C=GB/ST=London/L=London/O=Local/OU=Local/CN=127.0.0.1"
```
The `ssl` folder is ignored by `git` so you should not need to worry about committing the
generated key and certificate.

After generating the key and certificate, you are ready to run the application.

## Running
To run this application, you need to set some environment variables:
* `MONGO_USER` - The username for the MongoDB connection
* `MONGO_PASSWORD` - The password for the MongoDB connection
* `MONGO_HOST` - The host to connect to for the MongoDB connection
* `PRODUCT_IMAGE_URL_PREFIX` - Prefix for product images
* `SECRET_KEY` - Key used to sign session cookies
* `USERS_USER` - The username for the MongoDB users database connection
* `USERS_PASSWORD` - The password for the MongoDB users database connection
* `REDIS_DATA_URL` - The URL for the cache connection

The following environment variables are optional:
* `METRICS_USER` - The username for the MongoDB metrics database connection
* `METRICS_PASSWORD` - The password for the MongoDB metrics database connection
* `METRICS_HOST` - The host for the MongoDB metrics database connection

### Local

This is the run command you want for local dev:
`gunicorn -c config/gunicorn.conf.py "application:create_flask_app()"`

You should then be able to access the application at [http://0.0.0.0:5000](http://0.0.0.0:5000) in your browser.

## Tests
You can use [tox](https://tox.readthedocs.io/en/latest/) to run the tests in this repo.

First, install tox in the virtual environment:
```
pip install tox
```

Next, simply run `tox` in the root of the repo.
In addition to running the unit tests, code linting and formatting will be performed using
[isort](https://github.com/timothycrosley/isort), [black](https://github.com/psf/black),
and [flake8](https://flake8.pycqa.org/en/latest/).

## Database
This application creates a database called `test`.
It also creates a collection in that database called `test_collection`.

This application creates a TTL index on `test_collection` so documents created by this application will be
deleted after some time.

## Dependencies
This project's dependencies are laid out in the `requirements.in` file in the root of the repo.
These dependencies are not pinned to a particular version unless absolutely necessary.

To support repeatable builds, the `requirements.in` file is "compiled" to the frozen `requirements.txt` file.
This file pins every dependency to a particular version.

To update the `requirements.txt` file, use `pip-tools`:
```
pip install pip-tools
pip-compile --output-file=requirements.txt requirements.in
```

After updating the `requirements.txt` file, you should update your venv:
```
pip-sync requirements.txt
```
