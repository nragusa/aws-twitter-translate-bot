from datetime import datetime
from botocore.exceptions import ClientError
import boto3
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
SITE_PKGS = os.path.join(HERE, 'site-packages')
sys.path.append(SITE_PKGS)

import tweepy

DDB_TABLE = os.environ['DDB_TABLE']
TWITTER_BOT_HANDLE = os.environ['TWITTER_BOT_HANDLE']
SUPPORTED_LANGUAGES = ['ar', 'zh', 'fr', 'de', 'pt', 'es']


def extract_language(tweet):
    """ Parses the tweet for the first occurence of a hashtag
        and one of the supported languages. If no supported language
        is found, returns 'unknown'."""
    tweet = tweet.lower()
    words = tweet.split(' ')
    for word in words:
        if word.replace('#', '') in SUPPORTED_LANGUAGES:
            return word.replace('#', '')
    return 'unknown'


def sanitize_tweet(tweet, tweeter):
    """ Cleans up the translated tweet by ensuring punctuation is next
        to the letters, removes the Twitter Bot handle from the tweet
        so it doesn't get picked up again from the Zapier webhook,
        enters the source tweeter's username into the tweet so it's
        a proper response tweet, and splits the tweets into 2 if the
        resulting tweet is 280 characters or greater."""
    translated = re.sub(r'\s([?.!"](?:\s|$))', r'\1', tweet)
    translated = translated.replace(
        '@{}'.format(TWITTER_BOT_HANDLE), '')
    translated = translated.replace('# ar', '#ar').replace('# es', '#es').replace(
        '# fr', '#fr').replace('# pt', '#pt').replace('# de', '#de').replace('# zh', '#zh')
    translated = '@{} {}'.format(tweeter, translated)
    translated = translated.lstrip()
    if len(translated) > 280:
        for i in range(280, 0, -1):
            if translated[i] == ' ':
                tweets = [translated[:i], '@{} '.format(
                    tweeter) + translated[i:]]
                break
    else:
        tweets = [translated]
    return tweets


def translate_tweet(tweet, tweeter, language):
    """ Translates the tweet using Amazon Translate to the target
        language. If we could not extract the appropriate target
        language, we respond with a generic response and instructions
        on how to use the bot."""
    if language == 'unknown':
        return ("Hey! I didn't recognize the language you wanted me to translate that to. You can use "
                "any of #ar, #zh, #fr, #de, #pt, #es.")
    else:
        client = boto3.client('translate', region_name='us-east-1')
        try:
            response = client.translate_text(
                Text=tweet,
                SourceLanguageCode='en',
                TargetLanguageCode=language
            )
        except ClientError as error:
            print('Problem translating text: {}'.format(error))
            return ("Hey! I had a problem translating that one. Maybe another time?")
        else:
            translated_tweet = sanitize_tweet(
                response['TranslatedText'], tweeter)
            return translated_tweet


def save_tweet(tweet, tweeter, target_language, translated_tweet):
    """ Saves the original tweet, user, timestamp, target language,
        and translated tweet in a DynamoDB table."""
    ddb = boto3.resource('dynamodb')
    table = ddb.Table(DDB_TABLE)
    now = datetime.now().isoformat(' ').split('.')[0]
    print('Adding tweet {} with translation to {} to table'.format(
        tweet, target_language))
    try:
        table.put_item(
            Item={
                'screen_name': tweeter,
                'tweet': tweet,
                'date_tweeted': now,
                'target_language': target_language,
                'translated_tweet': ' '.join(translated_tweet)
            }
        )
    except ClientError as error:
        print('Problem updated DynamoDB table: {}'.format(error))


def reply_to_tweet(tweeter, translated_tweet, status_id):
    """ Takes the translated tweet(s), gets the encrypted consumer
        key and token, and access secret and token from SSM,
        then calls the Twitter API to respond back to the user
        with the translated tweet. """
    ssm = boto3.client('ssm')
    try:
        response = ssm.get_parameters(
            Names=[
                'sls.dev.twitter.translator.access.secret',
                'sls.dev.twitter.translator.access.token',
                'sls.dev.twitter.translator.consumer.key',
                'sls.dev.twitter.translator.consumer.secret'
            ],
            WithDecryption=True
        )
    except ClientError as error:
        print('Problem getting keys from SSM: {}'.format(error))
    else:
        params = response['Parameters']
        for param in params:
            if param['Name'].endswith('access.secret'):
                access_secret = param['Value']
            elif param['Name'].endswith('access.token'):
                access_token = param['Value']
            elif param['Name'].endswith('consumer.key'):
                consumer_key = param['Value']
            elif param['Name'].endswith('consumer.secret'):
                consumer_secret = param['Value']
            else:
                print('Unknown parmaeter passed: {}'.format(param))
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_secret)
        api = tweepy.API(auth)
        try:
            for status in translated_tweet[::-1]:
                print('Attempting to Tweet: {}'.format(status))
                api.update_status(
                    status=status,
                    in_reply_to_status_id=status_id
                )
        except tweepy.TweepError as error:
            print('Problem updating status: {}'.format(error))
        else:
            print('Successfully tweeted!')


def translate(event, context):
    """ Main function. Receives a webhook from Zapier whenver someone
        mentions @TWITTER_BOT_HANDLE in a tweet. Tweet must also include a 
        hashtag of the target language, e.g. #es to Spanish. If all the
        information is sent properly, this kicks off the translation,
        formation of a proper translated tweet (or tweets), stores it
        in a DynamoDB table, then returns OK."""
    body = json.loads(event['body'])
    if body['screen_name'] and body['tweet'] and body['status_id']:
        tweet = body['tweet']
        tweeter = body['screen_name']
        status_id = body['status_id']
        target_language = extract_language(tweet)
        translated_tweet = translate_tweet(tweet, tweeter, target_language)
        save_tweet(tweet, tweeter, target_language, translated_tweet)
        reply_to_tweet(tweeter, translated_tweet, status_id)
        response = {
            'statusCode': 200,
            'body': json.dumps('OK')
        }
    else:
        response = {
            'statusCode': 400,
            'body': json.dumps('Did not receive proper arguments')
        }
    return response
