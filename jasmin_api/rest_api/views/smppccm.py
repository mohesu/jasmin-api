import logging

from collections import OrderedDict

from django.conf import settings
from django.http import JsonResponse

from rest_api.exceptions import (
    JasminSyntaxError, JasminError, ActionFailed,
    ObjectNotFoundError, UnknownError, MissingKeyError,
    MultipleValuesRequiredKeyError
)
from rest_api.tools import set_ikeys, split_cols, sync_conf_instances

from rest_framework.decorators import action, parser_classes  # Replaced deprecated decorators
from rest_framework.parsers import JSONParser
from rest_framework.viewsets import ViewSet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT


class SMPPCCMViewSet(ViewSet):
    """
    ViewSet for managing SMPP Client Connectors via telnet commands.

    Supports listing, retrieving, creating, updating, starting, stopping, and deleting SMPP connectors.
    """
    lookup_field = 'cid'

    def get_smppccm(self, telnet, cid, silent=False):
        """
        Retrieve a single SMPP connector by its cid.

        :param telnet: The telnet connection to the Jasmin server.
        :param cid: Connector ID.
        :param silent: If True, do not raise an error if connector is not found.
        :return: A dict with connector attributes or None if not found and silent=True.
        :raises ObjectNotFoundError: If connector is not found and silent=False.
        """
        telnet.sendline(f'smppccm -s {cid}')
        matched_index = telnet.expect([
            rf'.+Unknown connector:.*{STANDARD_PROMPT}',
            rf'.+Usage:.*{STANDARD_PROMPT}',
            rf'(.+)\n{STANDARD_PROMPT}',
        ])

        if matched_index != 2:
            if silent:
                return None
            raise ObjectNotFoundError(f'Unknown connector: {cid}')

        result = telnet.match.group(1).decode('utf-8')
        smppccm = {}
        for line in result.splitlines():
            parts = [x for x in line.split() if x]
            if len(parts) == 2:
                key, value = parts
                smppccm[key] = value
        return smppccm

    def get_connector_list(self, telnet):
        """
        Retrieve a list of SMPP connectors from the telnet interface.

        :param telnet: The telnet connection to the Jasmin server.
        :return: A list of connector rows, each as a list of columns.
        """
        telnet.sendline('smppccm -l')
        telnet.expect([rf'(.+)\n{STANDARD_PROMPT}'])
        result = telnet.match.group(0).decode('utf-8').strip().replace("\r", '').split("\n")
        if len(result) < 3:
            return []
        return split_cols(result[2:-2])

    def simple_smppccm_action(self, telnet, telnet_list, action, cid):
        """
        Perform a simple action (e.g., remove, start, stop) on an SMPP connector.

        :param telnet: The telnet connection.
        :param telnet_list: List of telnet connections for syncing.
        :param action: The action character (e.g., 'r' for remove, '1' for start, '0' for stop).
        :param cid: Connector ID.
        :return: JsonResponse with the result.
        :raises:
            ObjectNotFoundError: If the connector does not exist.
            ActionFailed: If the action fails.
        """
        telnet.sendline(f'smppccm -{action} {cid}')
        matched_index = telnet.expect([
            rf'.+Successfully(.+){STANDARD_PROMPT}',
            rf'.+Unknown connector: (.+){STANDARD_PROMPT}',
            rf'(.*){STANDARD_PROMPT}',
        ])

        if matched_index == 0:
            # Action succeeded
            telnet.sendline('persist\n')
            telnet.expect(rf'.*{STANDARD_PROMPT}')
            if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
                sync_conf_instances(telnet_list)
            return JsonResponse({'name': cid})
        elif matched_index == 1:
            # Connector not found
            raise ObjectNotFoundError(f'Unknown SMPP Connector: {cid}')
        else:
            # Some other error message returned
            error_message = telnet.match.group(1).decode('utf-8').strip() if telnet.match.group(1).decode('utf-8') else 'Unknown error'
            raise ActionFailed(error_message)

    @action(detail=False, methods=['get'], url_path='status')
    def list_smppc_status(self, request):
        """
        List SMPP Client Connectors Status across all telnet instances.

        No parameters required.

        :return: JsonResponse with the status of all SMPP connectors across instances.
        """
        telnet_list = [request.telnet] + getattr(request, 'telnet_list', [])
        instances = []

        for telnet in telnet_list:
            connector_list = self.get_connector_list(telnet)
            connectors = []
            for raw_data in connector_list:
                if raw_data[0].startswith('#'):
                    connector = {
                        'cid': raw_data[0][1:],
                        'status': raw_data[1],
                        'session': raw_data[2]
                    }
                    connectors.append(connector)
            instances.append(connectors)

        return JsonResponse({'instances': instances})

    def list(self, request):
        """
        List all SMPP Client Connectors.

        No parameters required.
        Differentiates slightly from telnet CLI names and values:
            1. The "service" column is called "status".
            2. The cid is the full connector id of the form smpps(cid).
        """
        telnet = request.telnet
        connector_list = self.get_connector_list(telnet)
        connectors = []

        for raw_data in connector_list:
            if raw_data[0].startswith('#'):
                cid = raw_data[0][1:]
                connector = self.get_smppccm(telnet, cid, silent=True)
                if connector:
                    connector.update(
                        cid=cid,
                        status=raw_data[1],
                        session=raw_data[2],
                        starts=raw_data[3],
                        stops=raw_data[4]
                    )
                    connectors.append(connector)

        return JsonResponse({'connectors': connectors})

    def retrieve(self, request, cid):
        """
        Retrieve data for one SMPP connector by its cid.

        :param cid: Connector ID.
        :return: JsonResponse with the connector data.
        :raises ObjectNotFoundError: If the connector does not exist.
        """
        telnet = request.telnet
        connector = self.get_smppccm(telnet, cid, silent=False)
        connector_list = self.get_connector_list(telnet)

        list_data = next(
            (raw_data for raw_data in connector_list if raw_data[0] == f'#{cid}'),
            None
        )

        if not list_data:
            raise ObjectNotFoundError(f'Unknown connector: {cid}')

        connector.update(
            cid=cid,
            status=list_data[1],
            session=list_data[2],
            starts=list_data[3],
            stops=list_data[4]
        )

        return JsonResponse({'connector': connector})

    def create(self, request):
        """
        Create an SMPP Client Connector.

        Required parameter:
            - cid: Connector ID.

        Optional parameters:
            - (Additional parameters can be handled here if necessary.)

        :param request: DRF Request object containing the connector data.
        :return: JsonResponse with the created connector's cid.
        :raises MissingKeyError: If required parameters are missing.
        """
        telnet = request.telnet
        data = request.data

        # Validate required parameter 'cid'
        cid = data.get('cid')
        if not cid:
            raise MissingKeyError('Missing cid (connector identifier)')

        telnet.sendline('smppccm -a')
        telnet.expect(rf'Adding a new connector(.+)\n{INTERACTIVE_PROMPT}')

        # Set the 'cid' key
        set_ikeys(telnet, {"cid": cid})

        # Persist changes
        telnet.sendline('persist\n')
        telnet.expect(rf'.*{STANDARD_PROMPT}')

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(getattr(request, 'telnet_list', []))

        return JsonResponse({'cid': cid})

    def destroy(self, request, cid):
        """
        Delete an SMPP connector by its cid.

        HTTP response codes:
            - 200: Successful deletion.
            - 404: Nonexistent connector.
            - 400: Other errors.

        :param cid: Connector ID.
        :return: JsonResponse indicating the result.
        :raises ObjectNotFoundError: If the connector does not exist.
        :raises ActionFailed: If the deletion fails.
        """
        return self.simple_smppccm_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='r',
            cid=cid
        )

    @action(detail=True, methods=['put'], url_path='start')
    def start(self, request, cid):
        """
        Start an SMPP Connector.

        One parameter required: the connector identifier.

        HTTP response codes:
            - 200: Successful start.
            - 404: Nonexistent connector.
            - 400: Other errors (e.g., already started).
        """
        return self.simple_smppccm_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='1',
            cid=cid
        )

    @action(detail=True, methods=['put'], url_path='stop')
    def stop(self, request, cid):
        """
        Stop an SMPP Connector.

        One parameter required: the connector identifier.

        HTTP response codes:
            - 200: Successful stop.
            - 404: Nonexistent connector.
            - 400: Other errors (e.g., already stopped).
        """
        return self.simple_smppccm_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='0',
            cid=cid
        )

    @action(detail=True, methods=['patch'], parser_classes=[JSONParser])
    def custom_partial_update(self, request, cid):
        """
        Update some SMPP connector attributes.

        JSON requests only. The updates parameter is a key-value dictionary.

        :param cid: Connector ID.
        :param request: DRF Request object containing the updates.
        :return: JsonResponse with the updated connector data.
        :raises:
            JasminSyntaxError: If updates are malformed.
            UnknownError: If the connector does not exist.
            JasminError: For other errors returned by Jasmin.
        """
        telnet = request.telnet
        telnet.sendline(f'smppccm -u {cid}')
        matched_index = telnet.expect([
            rf'.*Updating connector(.*){INTERACTIVE_PROMPT}',
            rf'.*Unknown connector: (.*){STANDARD_PROMPT}',
            rf'.+(.*)(' + INTERACTIVE_PROMPT + '|' + STANDARD_PROMPT + ')',
            ])

        if matched_index == 1:
            raise UnknownError(detail=f'Unknown connector: {cid}')

        if matched_index != 0:
            raise JasminError(detail=" ".join(telnet.match.group(0).decode('utf-8').split()))

        updates = request.data

        # Validate that updates is a non-empty dictionary
        if not isinstance(updates, dict) or not updates:
            raise JasminSyntaxError('Updates should be a non-empty key-value dictionary')

        for key, value in updates.items():
            telnet.sendline(f"{key} {value}\n")
            matched_index = telnet.expect([
                rf'.*(Unknown SMPPClientConfig key:.*){INTERACTIVE_PROMPT}',
                rf'.*(Error:.*){STANDARD_PROMPT}',
                rf'.*{INTERACTIVE_PROMPT}',
                rf'.+(.*)(' + INTERACTIVE_PROMPT + '|' + STANDARD_PROMPT + ')',
                ])

            if matched_index != 2:
                error_detail = telnet.match.group(1).strip() if telnet.match.group(1).decode('utf-8') else 'Unknown error'
                raise JasminSyntaxError(detail=error_detail)

        # Complete the update process
        telnet.sendline('ok\n')
        ok_index = telnet.expect([
            rf'.*(Error:.*){STANDARD_PROMPT}',
            rf'(.*){INTERACTIVE_PROMPT}',
            rf'.*{STANDARD_PROMPT}',
        ])

        if ok_index == 0:
            error_detail = telnet.match.group(1).decode('utf-8').strip()
            raise JasminSyntaxError(detail=error_detail)

        telnet.sendline('persist\n')
        telnet.expect(rf'.*{STANDARD_PROMPT}')

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(getattr(request, 'telnet_list', []))

        updated_connector = self.get_smppccm(telnet, cid, silent=False)
        return JsonResponse({'connector': updated_connector})
