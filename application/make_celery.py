from application import create_flask_app

flask_app = create_flask_app()
celery_app = flask_app.extensions["celery"]
