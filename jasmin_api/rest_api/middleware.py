import pexpect
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from django.conf import settings

from .exceptions import TelnetUnexpectedResponse, TelnetConnectionTimeout, TelnetLoginFailed

if settings.JASMIN_K8S:
    try:
        config.load_incluster_config()
        k8s_api_obj = client.CoreV1Api()
        print "Main: K8S API initialized."
    except config.ConfigException as e:
        print "Main:ERROR: Cannot initialize K8S environment, terminating:", e
        sys.exit(-1)

class TelnetConnectionMiddleware(object):
    def process_request(self, request):
        """Add a telnet connection to all request paths that start with /api/
        assuming we only need to connect for these means we avoid unecessary
        overhead on any other functionality we add, and keeps URL path clear
        for it.
        """

        if not request.path.startswith('/api/'):
            return None

        if settings.JASMIN_DOCKER:
            request.telnet_list = []
            for port in settings.JASMIN_DOCKER_PORTS:
                telnet = self.telnet_request(settings.TELNET_HOST, port, settings.TELNET_USERNAME, settings.TELNET_PW)
                try:
                    telnet.expect_exact(settings.STANDARD_PROMPT)
                except pexpect.EOF:
                    raise TelnetLoginFailed
                else:
                    request.telnet = telnet
                    request.telnet_list.append(telnet)
        elif settings.JASMIN_K8S:
            if settings.DEBUG:
                print "Finding pods..."
            for host in self.set_telnet_list():
                telnet = self.telnet_request(host, settings.TELNET_PORT, settings.TELNET_USERNAME, settings.TELNET_PW)
                try:
                    telnet.expect_exact(settings.STANDARD_PROMPT)
                except pexpect.EOF:
                    raise TelnetLoginFailed
                else:
                    request.telnet = telnet
                    request.telnet_list.append(telnet)
            if settings.DEBUG:
                print "We find {} pods if telnet connection up".format(telnet_list.__length__)
        else:
            telnet = self.telnet_request(settings.TELNET_HOST, settings.TELNET_PORT, settings.TELNET_USERNAME, settings.TELNET_PW)
            try:
                telnet.expect_exact(settings.STANDARD_PROMPT)
            except pexpect.EOF:
                raise TelnetLoginFailed
            else:
                request.telnet = telnet

        if request.telnet === None:
            raise TelnetLoginFailed

        return None

    def set_telnet_list(self):
        api_response = k8s_api_obj.list_namespaced_pod(settings.JASMIN_K8S_NAMESPACE, label_selector="jasmin")
        msg = []
        for i in api_response.items:
            msg.append(i.metadata.name)
        return msg

    def telnet_request(self, host, port, user, pw):
        try:
            telnet = pexpect.spawn(
                "telnet %s %s" %
                (host, port),
                timeout=settings.TELNET_TIMEOUT,
            )
            telnet.expect_exact('Username: ')
            telnet.sendline(user)
            telnet.expect_exact('Password: ')
            telnet.sendline(pw)
        except pexpect.EOF:
            raise TelnetUnexpectedResponse
        except pexpect.TIMEOUT:
            raise TelnetConnectionTimeout
        
        return telnet

    def process_response(self, request, response):
        "Make sure telnet connection is closed when unleashing response back to client"
        if hasattr(request, 'telnet'):
            try:
                request.telnet.sendline('quit')
            except pexpect.ExceptionPexpect:
                request.telnet.kill(9)

        if hasattr(request, 'telnet_list'):
            for telnet in request.telnet_list:
                try:
                    request.telnet.sendline('quit')
                except pexpect.ExceptionPexpect:
                    request.telnet.kill(9)
                    
        return response
