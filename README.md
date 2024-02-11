# Pitemp Frontend
A simple Flask application to display temperature history.

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

## Running
To run this application, you need to set some environment variables:
* `MONGO_USER` - The username for the MongoDB connection
* `MONGO_PASSWORD` - The password for the MongoDB connection
* `MONGO_HOST` - The host to connect to for the MongoDB connection
* `SECRET_KEY` - Key used to sign session cookies
* `USERS_USER` - The username for the MongoDB users database connection
* `USERS_PASSWORD` - The password for the MongoDB users database connection
* `REDIS_DATA_URL` - The URL for the cache connection

### Local

You can run the application locally by executing the module `application`:
```
python3 -m application
```

By default, you can access the webapp by going to http://127.0.0.1:10000/

You can override this by setting the environment variables `WAITRESS_HOST` and `PORT`.
