import requests
import os
import sys
import subprocess
import json


logz_token = None
logz_csrf_token = None

def deploy(argv):
    lambda_name = argv[0]
    lambda_region = argv[1]
    print("Received lambda_name=" + lambda_name + " and lambda_region=" + lambda_region)
    result = subprocess.getoutput('aws apigateway get-rest-apis --region ' + lambda_region)
    if not lambda_name in result:
        print("Deploying the API gateway")
        invoke_url = deploy_api_gateway(lambda_name, lambda_region)
    else:
        print('Api gateway already existent... Not creating it')
        result_json = json.loads(result)
        for item in result_json['items']:
            if lambda_name in item['name']:
                invoke_url = gerenate_invoke_url(item['id'], lambda_region, lambda_name)
                break
    
    if logz_endpoint_exists(lambda_name):
        print('Logz endpoint already defined... Not creating it')
        return
    
    print("Deploying the Logz endpoint")
    print(deploy_logz(lambda_name, lambda_region, invoke_url).content.decode())
        

def deploy_api_gateway(lambda_name, lambda_region):
    result_json = execute_command_and_return_json('aws apigateway create-rest-api --name ' + lambda_name + '-API --description "Created from Gitlab CICD" --endpoint-configuration "{\\\"types\\\":[\\\"REGIONAL\\\"]}" --region ' + lambda_region)
    api_id = result_json['id']
    result_json = execute_command_and_return_json('aws apigateway get-resources --rest-api-id ' + api_id + ' --region ' + lambda_region)
    root_path_id = result_json['items'][0]['id']
    result_json = execute_command_and_return_json('aws apigateway create-resource --rest-api-id ' + api_id + ' --region ' + lambda_region + ' --parent-id ' + root_path_id + ' --path-part ' + lambda_name)
    resource_id = result_json['id']
    result_json = execute_command_and_return_json('aws apigateway put-method --rest-api-id ' + api_id + ' --resource-id ' + resource_id + ' --http-method ANY --authorization-type NONE --api-key-required --region ' + lambda_region)
    result_json = execute_command_and_return_json('aws apigateway put-method-response --rest-api-id ' + api_id + ' --resource-id ' + resource_id + ' --http-method ANY --status-code 200  --region ' + lambda_region)
    result_json = execute_command_and_return_json('aws sts get-caller-identity')
    account_id = result_json['Account']
    result_json = execute_command_and_return_json('aws apigateway put-integration --rest-api-id ' + api_id + ' --resource-id ' + resource_id + ' --http-method ANY --type AWS_PROXY --integration-http-method POST --uri "arn:aws:apigateway:' + lambda_region + ':lambda:path/2015-03-31/functions/arn:aws:lambda:' + lambda_region + ':' + account_id + ':function:' + lambda_name + '/invocations" --region ' + lambda_region)
    result_json = execute_command_and_return_json('aws apigateway create-deployment --rest-api-id ' + api_id + ' --region ' + lambda_region + ' --stage-name default --stage-description "Created by Gitlab CICD" --description "Created by Gitlab CICD"')
    result_json = execute_command_and_return_json('aws apigateway create-api-key --name ' + lambda_name + '-Key --enabled --description "Created by Gitlab CICD" --region ' + lambda_region)
    api_key_id = result_json['id']
    result_json = execute_command_and_return_json('aws apigateway create-usage-plan --name ' + lambda_name + '-UsagePlan --description "Created by Gitlab CICD" --api-stages apiId=' + api_id + ',stage=default --region ' + lambda_region)
    usage_plan_id = result_json['id']
    result_json = execute_command_and_return_json('aws apigateway create-usage-plan-key --usage-plan-id ' + usage_plan_id + ' --key-id ' + api_key_id + ' --key-type API_KEY --region ' + lambda_region)
    result_json = execute_command_and_return_json('aws lambda add-permission --function-name arn:aws:lambda:' + lambda_region + ':' + account_id +':function:' + lambda_name + ' --source-arn "arn:aws:execute-api:' + lambda_region + ':' + account_id +':' + api_id + '/*" --principal apigateway.amazonaws.com --statement-id 123456-96c3-4362-b900-860d14191d9f --action lambda:InvokeFunction --region ' + lambda_region)
    
    return gerenate_invoke_url(api_id, lambda_region, lambda_name)

def execute_command_and_return_json(command):
    result = subprocess.getoutput(command)
    print(command + '\n' + result)
    return json.loads(result)

def get_api_key(lambda_name, lambda_region):
    result_json = execute_command_and_return_json('aws apigateway get-api-keys --region ' + lambda_region)
    for item in result_json['items']:
        if lambda_name in item['name']:
            api_key_id = item['id']
            break
    result_json = execute_command_and_return_json('aws apigateway get-api-key --api-key ' + api_key_id + ' --include-value --region ' + lambda_region)
    return result_json['value']
    

def gerenate_invoke_url(api_id, lambda_region, lambda_name):
    return 'https://' + api_id + '.execute-api.' + lambda_region + '.amazonaws.com/default/' + lambda_name

def logs_logon():
    print("Logging in to logz")
    global logz_token
    global logz_csrf_token
    username = os.getenv('LOGZ_USERNAME')
    password = os.getenv('LOGZ_PASSWORD')
    url='https://app.logz.io/'
    result = requests.get(url)
    cookies_orig = result.cookies
    csrf_token = result.cookies['Logzio-Csrf']
    
    url = 'https://logzio.auth0.com/oauth/ro'
    data = {
        'scope': 'openid email connection',
        'response_type': 'token',
        'connection': 'Username-Password-Authentication',
        'username': username,
        'password': password,
        'callbackURL': 'https://app.logz.io/login/auth0code/baseUrl/https%3A%2F%2Fapp.logz.io',
        'responseType': 'token',
        'popup': 'false',
        'sso': 'false',
        'mfa_code': '',
        'client_id': 'kydHH8LqsLR6D6d2dlHTpPEdf0Bztz4c',
        'grant_type': 'password'
    }
    headers = {
        'Auth0-Client': 'eyJuYW1lIjoiYXV0aDAuanMiLCJ2ZXJzaW9uIjoiNy42LjEifQ',
    }
    result = requests.post(url,data,cookies=cookies_orig,headers=headers)
    result_json = json.loads(result.content.decode())
    cookies = result.cookies
    id_token = result_json['id_token']
    
    url = 'https://app.logz.io/login/jwt'
    data = {
        'jwt': id_token
    }
    headers = {
        'accept': 'application/json',
        'x-logz-csrf-token': csrf_token
    }
    
    result = requests.post(url, data, cookies=cookies_orig, headers=headers)
    result_json = json.loads(result.content.decode())
    logz_token = result_json['sessionToken']
    logz_csrf_token = csrf_token

def logz_endpoint_exists(lambda_name):
    global logz_token
    global logz_csrf_token
    if not logz_token or not logz_csrf_token:
        logs_logon()
    headers = {
        'X-AUTH-TOKEN' : logz_token,
        'accept': 'application/json',
        'X-Logz-CSRF-Token': logz_csrf_token
    }
    url = 'https://app.logz.io/endpoints'
    result = requests.get(url, headers=headers)
    result_json = json.loads(result.content.decode())
    for item in result_json:
        if lambda_name in item['url']:
            return True
    return False
        

def deploy_logz(lambda_name, lambda_region, invoke_url):
    global logz_token
    global logz_csrf_token
    if not logz_token or not logz_csrf_token:
        logs_logon()
        
    headers = {
        'X-AUTH-TOKEN' : logz_token,
        'accept': 'application/json',
        'X-Logz-CSRF-Token': logz_csrf_token
    }
    cookies = {
        "Logzio-Csrf": logz_csrf_token
    }
    url = 'https://app.logz.io/endpoints/custom'
    data = {
        "title": lambda_name + " Lambda",
        "description": "Deployed with Gitlab CICD",
        "url": invoke_url,
        "method": "POST",
        "headers": "x-api-key=" + get_api_key(lambda_name, lambda_region),
        "bodyTemplate": {
            "alert_title":"{{alert_title}}",
            "alert_description":"{{alert_description}}",
            "alert_severity":"{{alert_severity}}",
            "alert_event_samples":"{{alert_event_samples}}"
        }
    }
    
    return requests.post(url, json.dumps(data), headers=headers, cookies=cookies)

if __name__ == '__main__':
   deploy(sys.argv[1:])