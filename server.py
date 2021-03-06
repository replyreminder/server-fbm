# stdlib imports
import os
import json

# flask imports
from flask import Flask,  jsonify, request, abort
from flask_restful import reqparse
from flask_cors import CORS
from flask_autodoc import Autodoc

# sql exceptions
from sqlalchemy import exc

# project imports
from replyreminder.models import db, Person, Reminder
from sendReminders import sendLoginButton, getPSID, getUserId

# app setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
CORS(app)
db.init_app(app)
auto = Autodoc(app)

with app.app_context():
    db.create_all()

# parser args
parser = reqparse.RequestParser()
parser.add_argument('userid')
parser.add_argument('account_linking_token')
parser.add_argument('auth_token')
parser.add_argument('gsid')
parser.add_argument('psid')
parser.add_argument('email')
parser.add_argument('first_name')
parser.add_argument('last_name')
parser.add_argument('timezone')
parser.add_argument('updated_time')
parser.add_argument('followupUsername')
parser.add_argument('reminderTime')
parser.add_argument('notes')
parser.add_argument('reminderid')
parser.add_argument('hub.mode')
parser.add_argument('hub.challenge')
parser.add_argument('hub.verify_token')



@app.route("/")
def test():
    return auto.html()


@app.route("/user/", methods=['POST'])
@auto.doc()
def createUser():
    """
    Json input {userid int, email string, first_name string, last_name string, timezone string, updated_timedatetime}
    Responses 200 user successfully created or already exists, 400 malformed json input, 500 who knows?
    """
    args = parser.parse_args()
    if not args['userid']:
        return jsonify(success=False), 400

    if Person.query.filter_by(userid=args['userid']).first():
        return jsonify(success=True), 200

    try:
        db.session.add(Person(userid=args['userid'], email=args['email'],
                            first_name=args['first_name'], last_name=args['last_name'],
                            timezone=args['timezone'], updated_time=args['updated_time']))
        db.session.commit()
    except exc.IntegrityError as e:
        # Malformed Entry
        print(e)
        return jsonify(success=False), 400

    except Exception as e:
        print(e)
        return jsonify(success=False), 500

    return jsonify(success=True), 200


@app.route("/reminder/", methods=['POST'])
@auto.doc()
def createReminder():
    """
    expects: {userid: int, followupUsername: string, reminderTime: datetime, notes: string(optional)}
    returns: 200: reminder was successfully added 400: malformed json 500: unknown server error (DB)
    """
    args = parser.parse_args()
    if not args['auth_token']:
        return jsonify(success=False), 400

    if not args['userid']:
        return jsonify(success=False), 400

    user = Person.query.filter_by(gsid=args['userid']).first()

    if getUserId(args['auth_token']) != user.gsid:
        return jsonify(success=False, msg="invalid auth_token for userid"), 400

    if not user:
        return jsonify(success=False), 400

    args['userid'] = user.psid  # switching from gsid to psid

    try:
        # todo: find some super cool way to do this
        db.session.add(Reminder(userid=args['userid'], followupUsername=args['followupUsername'],
                                       reminderTime=args['reminderTime'], notes=args['notes']))
        db.session.commit()

    except exc.IntegrityError as e:
        # Malformed Entry
        print(e)
        return jsonify(success=False), 400

    except Exception as e:
        print(e)
        return jsonify(success=False), 500

    return jsonify(success=True), 200


@app.route("/reminders/", methods=["GET"])
@auto.doc()
def getReminders():
    """
    The endpoint for getting requests
    return: [{userId:int, reminderTime: datetime, followupUsername: string, notes: string}]
    """
    try:
        result = [x.__dict__ for x in Reminder.query.filter_by(sent=False).all()]
        # todo: figure out how to not have this in the result in the first place
        for x in result:
            x.pop('_sa_instance_state', None)

    except Exception as e:
        print(e)
        return jsonify(success=False), 500

    return jsonify(result), 200


@app.route("/reminder/sent/", methods=["POST"])
@auto.doc()
def markReminderSent():
    """
    :return:
    """
    args = parser.parse_args()
    if not args['reminderid']:
        return jsonify(success=False), 400

    try:
        reminder = Reminder.query.filter_by(id=args['reminderid']).first()
        reminder.sent = True
        db.session.commit()

    except exc.IntegrityError:
        return jsonify(success=False), 400

    except Exception as e:
        print(e)
        return jsonify(success=False), 500

    return jsonify(success=True), 200

@app.route('/linkaccount/', methods=['POST'])
@auto.doc()
def linkAccount():
    args = parser.parse_args()
    if 'gsid' not in args or 'account_linking_token' not in args:
        return jsonify(success=False), 400

    if getUserId(args['auth_token']) != args['gsid']:
        return jsonify(success=False, msg="invalid auth_token for userid"), 400

    psid = getPSID(args['account_linking_token'])

    user = Person.query.filter_by(gsid=args['gsid']).first()
    if user:
        # user already exists
        if user.psid != psid:
            user.psid = psid
        try:
            db.session.commit()
        except Exception as e:
            print(e)
            return jsonify(success=False), 500

    else:
        newUser = Person(gsid=args['gsid'], psid=psid)
        try:
            db.session.add(newUser)
            db.session.commit()
        except Exception as e:
            print(e)
            return jsonify(success=False), 500

    return jsonify(success=True), 200

@app.route('/<path:path>')
def catch_all(path):
    print("catch path")
    print(path)
    return jsonify(success=False), 404

@app.route("/webhook/", methods=['GET'])
@auto.doc()
def webhookGet():
    args = parser.parse_args()
    if args['hub.mode'] == "subscribe" and args['hub.verify_token'] == 'this_is_the_verify_token_my_dude':
        return jsonify(int(args['hub.challenge'])), 200

    return jsonify(success=False), 403


@app.route("/webhook/", methods=["POST"])
@auto.doc()
def webhookPost():
    body = json.loads(request.data)
    print(body)
    if body['object'] == "page":
        for each in body['entry']:
            for messagingEvent in each['messaging']:
                if 'postback' in messagingEvent:
                    print("This is a postback")
                    print(messagingEvent)
                    if messagingEvent['postback']['payload'] == 'get_started':
                        print("sending login button")

                        sendLoginButton(messagingEvent['sender']['id'])

                elif 'message' in messagingEvent:
                    print("This is a message")
                    print(messagingEvent)

                else:
                    print("I have no clue what this is")
                    print(messagingEvent)

    else:
        return jsonify(success=False), 404

    return jsonify(success=True), 200


def main():
    app.run(host='0.0.0.0')

if __name__ == "__main__":
    main()