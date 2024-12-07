import logging

from collections import OrderedDict

from django.conf import settings
from django.http import JsonResponse
from django.utils.datastructures import MultiValueDictKeyError

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action  # Replaces the deprecated list_route

from rest_api.exceptions import (
    JasminSyntaxError, JasminError, UnknownError, MissingKeyError,
    MutipleValuesRequiredKeyError, ObjectNotFoundError
)
from rest_api.tools import set_ikeys, split_cols, sync_conf_instances

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT


class MORouterViewSet(ViewSet):
    """
    ViewSet for managing MO (Mobile Originated) Routes.

    Allows listing, retrieving, creating, flushing, and deleting MO routes.
    """
    lookup_field = 'order'

    def _list(self, telnet):
        """
        List all MO routes as a Python dictionary.

        :param telnet: The telnet connection to the Jasmin server.
        :return: A dict with a 'morouters' key containing a list of routes.
        """
        telnet.sendline('morouter -l')
        telnet.expect([r'(.+)\n' + STANDARD_PROMPT])
        result = telnet.match.group(0).strip().replace("\r", '').split("\n")

        # If fewer than 3 lines, it means no routes were returned
        if len(result) < 3:
            return {'morouters': []}

        # Clean and parse the results
        cleaned_lines = [l.replace(', ', ',').replace('(!)', '') for l in result[2:-2] if l]
        routers = split_cols(cleaned_lines)
        return {
            'morouters': [
                {
                    'order': r[0].strip().lstrip('#'),
                    'type': r[1],
                    'connectors': [c.strip() for c in r[2].split(',')],
                    'filters': ([f.strip() for f in ' '.join(r[3:]).split(',')] if len(r) > 3 else [])
                } for r in routers
            ]
        }

    def list(self, request):
        """
        List all MO routers.

        No parameters required.
        """
        return JsonResponse(self._list(request.telnet))

    def get_router(self, telnet, order):
        """
        Retrieve data for a single MO router identified by 'order'.

        :param telnet: Telnet connection.
        :param order: The order (string) of the desired MO router.
        :return: A dict with the 'morouter' key representing the router data.
        :raises ObjectNotFoundError: If no router is found with the given order.
        """
        morouters = self._list(telnet)['morouters']
        router = next((m for m in morouters if m['order'] == order), None)
        if router is None:
            raise ObjectNotFoundError(f'No MO Router with order: {order}')
        return {'morouter': router}

    def retrieve(self, request, order):
        """
        Retrieve details for a single MO router by its order (integer/string).

        :param order: The router's order identifier.
        """
        return JsonResponse(self.get_router(request.telnet, order))

    @action(detail=False, methods=['delete'])
    def flush(self, request):
        """
        Flush the entire MO routing table.

        After flushing, persist changes and sync configurations if applicable.
        """
        telnet = request.telnet
        telnet.sendline('morouter -f')
        telnet.expect([r'(.+)\n' + STANDARD_PROMPT])
        telnet.sendline('persist\n')
        telnet.expect(r'.*' + STANDARD_PROMPT)

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(request.telnet_list)

        return JsonResponse({'morouters': []})

    def create(self, request):
        """
        Create a new MO Router.

        Required parameters: type, order
        Additional parameters depend on type:
        - If type != 'DefaultRoute', filters are required.
        - Connectors are required: at least one for other routes, at least two for RandomRoundrobinMORoute.
        """
        telnet = request.telnet
        data = request.data

        # Validate required parameters
        try:
            rtype = data['type'].lower()
            order = data['order']
        except KeyError:
            raise MissingKeyError('Missing parameter: type or order is required')

        telnet.sendline('morouter -a')
        telnet.expect(r'Adding a new MO Route(.+)\n' + INTERACTIVE_PROMPT)

        ikeys = OrderedDict({'type': rtype})
        if rtype != 'defaultroute':
            # Filters are required for all routes except DefaultRoute
            try:
                filters = data['filters'].split(',')
            except (MultiValueDictKeyError, AttributeError):
                raise MissingKeyError(f'{rtype} router requires filters')
            ikeys['filters'] = ';'.join(filters)
            ikeys['order'] = order
            logger.info("Setting keys for MO router: %s", ikeys)

        # Handle connectors
        smppconnectors = data.get('smppconnectors', '')
        httpconnectors = data.get('httpconnectors', '')
        connectors = [f'smpps({c.strip()})' for c in smppconnectors.split(',') if c.strip()] + \
                     [f'http({c.strip()})' for c in httpconnectors.split(',') if c.strip()]

        if rtype == 'randomroundrobinmoroute':
            # At least two connectors needed for round robin
            if len(connectors) < 2:
                raise MutipleValuesRequiredKeyError(
                    'RandomRoundrobinMORoute requires at least two connectors')
            ikeys['connectors'] = ';'.join(connectors)
        else:
            # Exactly one connector is required for other route types
            if len(connectors) != 1:
                raise MissingKeyError('One and only one connector is required')
            ikeys['connector'] = connectors[0]

        set_ikeys(telnet, ikeys)
        telnet.sendline('persist\n')
        telnet.expect(r'.*' + STANDARD_PROMPT)

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(request.telnet_list)

        return JsonResponse({'morouter': self.get_router(telnet, order)})

    def simple_morouter_action(self, telnet, telnet_list, action, order, return_moroute=True):
        """
        Perform a simple action (e.g., remove) on a MO router.

        :param telnet: Telnet connection.
        :param telnet_list: List of telnet connections for syncing.
        :param action: The action character (e.g., 'r' for remove).
        :param order: The order identifier of the router.
        :param return_moroute: If True, return the updated router data after the action.
        """
        telnet.sendline(f'morouter -{action} {order}')
        matched_index = telnet.expect([
            r'.+Successfully(.+)' + STANDARD_PROMPT,
            r'.+Unknown MO Route: (.+)' + STANDARD_PROMPT,
            r'.+(.*)' + STANDARD_PROMPT,
            ])

        if matched_index == 0:
            # Action succeeded
            telnet.sendline('persist\n')
            telnet.expect(r'.*' + STANDARD_PROMPT)

            if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
                sync_conf_instances(telnet_list)

            if return_moroute:
                return JsonResponse({'morouter': self.get_router(telnet, order)})
            else:
                return JsonResponse({'order': order})
        elif matched_index == 1:
            # Unknown router error
            raise UnknownError(detail=f'No router: {order}')
        else:
            # Other Jasmin-related error
            raise JasminError(telnet.match.group(1))

    def destroy(self, request, order):
        """
        Delete a MO router by order.

        HTTP status codes:
        - 200: Successful deletion
        - 404: Nonexistent router
        - 400: Other error
        """
        return self.simple_morouter_action(request.telnet, request.telnet_list, 'r', order, return_moroute=False)
