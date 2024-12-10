import logging

from django.conf import settings
from django.http import JsonResponse

from rest_framework.viewsets import ViewSet

from rest_api.exceptions import (
    JasminSyntaxError, JasminError, ActionFailed,
    ObjectNotFoundError, UnknownError
)
from rest_api.tools import set_ikeys, split_cols, sync_conf_instances

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT


class HTTPCCMViewSet(ViewSet):
    """
    ViewSet for managing HTTP Client Connectors via telnet commands.

    Supported actions:
    - list: List all connectors
    - retrieve: Get details of a single connector
    - create: Add a new connector
    - destroy: Remove an existing connector
    """
    lookup_field = 'cid'

    def get_httpccm(self, telnet, cid, silent=False):
        """
        Retrieve a single HTTP connector by its cid.

        :param telnet: The telnet connection
        :param cid: Connector ID
        :param silent: If True, do not raise an error if connector is not found
        :return: A dict with connector attributes
        """
        telnet.sendline(f'httpccm -s {cid}')
        matched_index = telnet.expect([
            r'.+Unknown connector:.*' + STANDARD_PROMPT,
            r'.+Usage:.*' + STANDARD_PROMPT,
            r'(.+)\n' + STANDARD_PROMPT,
            ])

        if matched_index != 2:
            # Connector not found or invalid usage
            if silent:
                return None
            raise ObjectNotFoundError(f'Unknown connector: {cid}')

        # Parse connector details line by line
        result = telnet.match.group(1).decode('utf-8')
        httpccm = {}
        for line in result.splitlines():
            parts = [x for x in line.split() if x]
            if len(parts) == 2:
                key, value = parts
                httpccm[key] = value
        return httpccm

    def get_connector_list(self, telnet):
        """
        Retrieve a raw list of connectors from the telnet interface.
        :return: A list of lists representing connector rows.
        """
        telnet.sendline('httpccm -l')
        telnet.expect([r'(.+)\n' + STANDARD_PROMPT])
        result = telnet.match.group(0).decode('utf-8').strip().replace("\r", '').split("\n")
        if len(result) < 3:
            # No connectors found
            return []
        return split_cols(result[2:-2])

    def simple_httpccm_action(self, telnet, telnet_list, action, cid):
        """
        Perform a simple httpccm action (like remove) and return a JSON response.

        :param telnet: The telnet connection
        :param telnet_list: The list of telnet connections for sync
        :param action: Action character (e.g., 'r' for remove)
        :param cid: Connector ID
        """
        telnet.sendline(f'httpccm -{action} {cid}')
        matched_index = telnet.expect([
            r'.+Successfully(.+)' + STANDARD_PROMPT,
            r'.+Unknown connector: (.+)' + STANDARD_PROMPT,
            r'(.*)' + STANDARD_PROMPT,
            ])

        if matched_index == 0:
            # Action succeeded
            telnet.sendline('persist\n')
            telnet.expect(r'.*' + STANDARD_PROMPT)
            if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
                sync_conf_instances(telnet_list)
            return JsonResponse({'name': cid})
        elif matched_index == 1:
            # Connector not found
            raise ObjectNotFoundError(f'Unknown HTTP Connector: {cid}')
        else:
            # Some other error message returned
            raise ActionFailed(telnet.match.group(1).decode('utf-8'))

    def list(self, request):
        """
        List all HTTP Client Connectors.
        No parameters required.
        """
        telnet = request.telnet
        connector_list = self.get_connector_list(telnet)
        connectors = []

        for raw_data in connector_list:
            if raw_data[0].startswith('#'):
                # Extracting connector info
                cid = raw_data[0][1:]
                connector = self.get_httpccm(telnet, cid, silent=True)
                if connector is not None:
                    connector.update(
                        cid=cid,
                        type=raw_data[1],
                        method=raw_data[2],
                        url=raw_data[3]
                    )
                    connectors.append(connector)
        return JsonResponse({'connectors': connectors})

    def retrieve(self, request, cid):
        """
        Retrieve data for a single connector by cid.
        Required parameter: cid (connector id)
        """
        telnet = request.telnet
        connector = self.get_httpccm(telnet, cid, silent=False)
        connector_list = self.get_connector_list(telnet)

        # Find additional info from the list
        list_data = next((raw for raw in connector_list if raw[0] == '#' + cid), None)
        if not list_data:
            raise ObjectNotFoundError(f'Unknown connector: {cid}')

        connector.update(
            cid=cid,
            type=list_data[1],
            method=list_data[2],
            url=list_data[3]
        )
        return JsonResponse({'connector': connector})

    def create(self, request):
        """
        Create a new HTTP Client Connector.

        Required parameters: cid, url, method
        """
        telnet = request.telnet
        data = request.data

        telnet.sendline('httpccm -a')
        # Send each provided parameter line by line
        for k, v in data.items():
            telnet.sendline(f"{k} {v}")

        # Complete the action
        telnet.sendline('ok')
        matched_index = telnet.expect([
            r'.*(HttpConnector url syntax is invalid.*)' + INTERACTIVE_PROMPT,
            r'.*(HttpConnector method syntax is invalid, must be GET or POST.*)' + INTERACTIVE_PROMPT,
            r'.*' + INTERACTIVE_PROMPT,
            r'.+(.*)(' + INTERACTIVE_PROMPT + '|' + STANDARD_PROMPT + ')',
            ])

        if matched_index != 2:
            # Syntax error in parameters
            raise JasminSyntaxError(detail=" ".join(telnet.match.group(1).decode('utf-8').split()))

        # Persist changes
        telnet.sendline('persist\n')
        telnet.expect(r'.*' + STANDARD_PROMPT)
        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(request.telnet_list)

        return JsonResponse({'cid': request.data['cid']})

    def destroy(self, request, cid):
        """
        Delete an HTTP connector by its cid.

        Response codes:
        - 200: Successfully deleted
        - 404: Nonexistent connector
        - 400: Other error
        """
        return self.simple_httpccm_action(request.telnet, request.telnet, 'r', cid)
