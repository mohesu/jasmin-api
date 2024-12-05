import pexpect
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from .exceptions import (
    TelnetUnexpectedResponse,
    TelnetConnectionTimeout,
    TelnetLoginFailed,
)


class TelnetConnectionMiddleware(MiddlewareMixin):
    """
    Middleware to manage Telnet connections for requests starting with /api/.
    """

    def process_request(self, request):
        """
        Add a Telnet connection to all request paths that start with /api/.
        Avoid unnecessary overhead for other paths and functionalities.
        """
        if not request.path.startswith('/api/'):
            return None

        request.telnet = None

        if settings.DEBUG:
            print(f"settings.JASMIN_DOCKER: {settings.JASMIN_DOCKER}")
            print(f"settings.JASMIN_K8S: {settings.JASMIN_K8S}")

        if settings.JASMIN_DOCKER:
            request.telnet_list = []
            for port in settings.JASMIN_DOCKER_PORTS:
                telnet = self.telnet_request(
                    settings.TELNET_HOST,
                    port,
                    settings.TELNET_USERNAME,
                    settings.TELNET_PW
                )
                try:
                    telnet.expect_exact(settings.STANDARD_PROMPT)
                except pexpect.EOF:
                    raise TelnetLoginFailed
                else:
                    if request.telnet is None:
                        request.telnet = telnet
                    else:
                        request.telnet_list.append(telnet)
            if request.telnet is None:
                raise TelnetLoginFailed
            return None

        if settings.JASMIN_K8S:
            request.telnet_list = []
            all_pods = self.set_telnet_list()
            if settings.DEBUG:
                print(f"Finding pods... Found {len(all_pods)} pods in K8s.")
            for host in all_pods:
                telnet = self.telnet_request(
                    host,
                    settings.TELNET_PORT,
                    settings.TELNET_USERNAME,
                    settings.TELNET_PW
                )
                try:
                    telnet.expect_exact(settings.STANDARD_PROMPT)
                except pexpect.EOF:
                    raise TelnetLoginFailed
                else:
                    if request.telnet is None:
                        request.telnet = telnet
                    else:
                        request.telnet_list.append(telnet)
            if request.telnet is None:
                raise TelnetLoginFailed
            if settings.DEBUG:
                print(f"Found {len(request.telnet_list)} pods with Telnet connection up.")
            return None

        # Default Telnet connection for non-Docker, non-K8s setups
        telnet = self.telnet_request(
            settings.TELNET_HOST,
            settings.TELNET_PORT,
            settings.TELNET_USERNAME,
            settings.TELNET_PW
        )
        try:
            telnet.expect_exact(settings.STANDARD_PROMPT)
        except pexpect.EOF:
            raise TelnetLoginFailed
        else:
            request.telnet = telnet

        if request.telnet is None:
            raise TelnetLoginFailed

        return None

    def set_telnet_list(self):
        """
        Fetch pod IPs from the Kubernetes namespace with the label 'jasmin'.
        """
        try:
            api_response = settings.K8S_CLIENT.list_namespaced_pod(
                settings.JASMIN_K8S_NAMESPACE,
                label_selector="jasmin"
            )
        except ApiException as e:
            if settings.DEBUG:
                print(f"API Exception while listing pods: {e}")
            raise TelnetUnexpectedResponse(detail="Failed to list pods from Kubernetes.")

        if settings.DEBUG:
            print(f"Response K8S: {len(api_response.items)} pods found.")

        pod_ips = [
            item.status.pod_ip
            for item in api_response.items
            if hasattr(item, "status") and item.status.pod_ip
        ]

        if not pod_ips:
            raise TelnetLoginFailed(detail="No Jasmin pods found in Kubernetes.")

        return pod_ips

    def telnet_request(self, host, port, user, pw):
        """
        Establish a Telnet connection and authenticate.
        """
        try:
            telnet = pexpect.spawn(
                f"telnet {host} {port}",
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
        """
        Ensure Telnet connections are closed when the response is sent.
        """
        if hasattr(request, 'telnet') and request.telnet is not None:
            try:
                request.telnet.sendline('quit')
                request.telnet.expect_exact(settings.STANDARD_PROMPT)
            except pexpect.ExceptionPexpect:
                request.telnet.kill(9)

        if hasattr(request, 'telnet_list'):
            for telnet in request.telnet_list:
                try:
                    telnet.sendline('quit')
                    telnet.expect_exact(settings.STANDARD_PROMPT)
                except pexpect.ExceptionPexpect:
                    telnet.kill(9)

        return response
