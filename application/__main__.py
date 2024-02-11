import waitress

from application import create_flask_app


def main():
    waitress.serve(create_flask_app(), listen='127.0.0.1:5003')


if __name__ == '__main__':
    main()
