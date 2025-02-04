import boto3
import requests
from flask import Flask, request, Response

app = Flask(__name__)

# Define a whitelist of allowed hosts
whitelisted_hosts = [
    "auth-preprod",  # Example of a whitelisted service
    "example.com"    # Add more hosts as needed
]

# AWS Cloud Map Service Discovery
def discover_service_instance(service_name):
    client = boto3.client('servicediscovery')
    try:
        # Replace with your Cloud Map namespace
        namespace_name = 'pre-prod-eloelo'

        # Discover instances of the ECS service
        response = client.discover_instances(
            NamespaceName=namespace_name,
            ServiceName=service_name
        )

        # Extract the host IP and mapped port from the first available instance
        instances = response['Instances']
        if instances:
            attributes = instances[0]['Attributes']
            host_ip = attributes.get('AWS_INSTANCE_IPV4')  # The host's IP address
            port = attributes.get('AWS_INSTANCE_PORT')     # The mapped port on the host
            return host_ip, port
        return None, None
    except Exception as e:
        print(f"Error discovering instances: {e}")
        return None, None

# Intercept request and forward it to resolved host IP and port
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    # Extract the service name from the host
    service_name = request.host.split(':')[0]  

    # Check if the service name is in the whitelist
    if service_name not in whitelisted_hosts:
        return Response(f"Host {service_name} is not allowed.", status=403)

    # Discover the service instance IP and port
    host_ip, mapped_port = discover_service_instance(service_name)

    if not host_ip or not mapped_port:
        return Response("Service instance not found", status=404)

    # Forward the request to the resolved host IP and port
    url = f"http://{host_ip}:{mapped_port}/{path}"
    headers = {key: value for key, value in request.headers if key != 'Host'}

    # Forward request with the same method
    try:
        if request.method == 'GET':
            resp = requests.get(url, headers=headers, params=request.args, stream=True)
        elif request.method == 'POST':
            resp = requests.post(url, headers=headers, json=request.get_json(), stream=True)
        elif request.method == 'PUT':
            resp = requests.put(url, headers=headers, json=request.get_json(), stream=True)
        elif request.method == 'DELETE':
            resp = requests.delete(url, headers=headers, stream=True)
        elif request.method == 'PATCH':
            resp = requests.patch(url, headers=headers, json=request.get_json(), stream=True)
        else:
            return Response("Method not allowed", status=405)

        # Remove Transfer-Encoding header if present
        if 'Transfer-Encoding' in resp.headers:
            del resp.headers['Transfer-Encoding']

        # Return the full response content as a single chunk
        return Response(
            resp.content,  # Stream the full content as a single response
            status=resp.status_code,
            headers=dict(resp.headers)
        )

    except Exception as e:
        return Response(f"Error forwarding request: {str(e)}", status=500)

# Start the Flask server to act as a proxy
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

