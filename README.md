## Overview

This is a serverless application that will translate a tweet into another language using Amazon Translate. When a user includes @MyTranslatorBot, along with a hashtag + language code (e.g. #fr for French), [Zapier.com](https://zapier.com) will fire a webhook to the API Gateway endpoint that will invokde the Lambda function. The Lambda function is responsible for parsing the tweet, translating it, sanitizing the tweet before responding, saving it off into DynamoDB, then replying to the tweet with the translation. This application was built using the very awesome [Serverless Framework](https://serverless.com).

## Prerequisites

You'll need the [Serverless Framework installed](https://serverless.com/framework/docs/providers/aws/guide/installation/) first, and properly set up your AWS credentials.

You'll also need to create a [Twitter application](https://apps.twitter.com/) and generate the appropriate access keys.

Finally, you'll need to create a [Zapier.com](https://zapier.com) account, and connect it to your Twitter application. They have built in integrations that walk you through setting this up. I used the Twitter @mention -> webhook integration.

## Setup

Clone the repository, then create a virtualenv and install the tweepy module:

```
virtualenv venv
source venv/bin/activate
pip install tweepy
```

To keep my workspace clean, I like to create a symlink to site-packages in the directory, which will automatically get included in the deployment package as specified in the serverless.yml file:

```
ln -s venv/path/to/site-packages site-packages
```

Now you can deploy the application into your AWS account. Assuming you've cloned this repository first:

```
sls deploy -v -s dev
```

## Final Configuration

Now that the application is deployed, you need to store your Twitter credentials in AWS Systems Manager Parameter Store. I've found it's easiest to do this via the [AWS CLI](https://docs.aws.amazon.com/cli/latest/reference/ssm/put-parameter.html). Create the following parameters, being sure to specify the key ID created from the serverless deployment!

* sls.dev.twitter.translator.access.secret
* sls.dev.twitter.translator.access.token
* sls.dev.twitter.translator.consumer.key
* sls.dev.twitter.translator.consumer.secret

Example:

```
aws ssm put-parameter --name sls.dev.twitter.translator.access.secret --value 'supercrazysecretfromtwitterapp' --type SecureString --key-id 'keyidfromserverlessdeployment'
```

Finally, create the webhook integration in Zapier. Be sure to provide the following:

* Include the **status** (tweet), **screen_name**, and **status_id** in the first step of the workflow
* Specify the payload type as JSON
* For data, specify **tweet**, **screen_name**, and **status_id** as the variable names, and the appropriate values from step 1. Make sure you use those exact names as the function expects them!
* In the headers, specify a custom header of **x-api-key** and the API key value displayed when you deployed the serverless application.

Be sure to run a test from the Zapier console first!
