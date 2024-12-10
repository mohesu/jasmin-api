import logging

from collections import OrderedDict

from django.conf import settings
from django.http import JsonResponse
from django.utils.datastructures import MultiValueDictKeyError

from rest_api.exceptions import (
    JasminSyntaxError, JasminError,
    UnknownError, MissingKeyError,
    MultipleValuesRequiredKeyError, ObjectNotFoundError
)
from rest_api.tools import set_ikeys, split_cols, sync_conf_instances

from rest_framework.decorators import action  # Use @action instead of deprecated @list_route
from rest_framework.parsers import JSONParser
from rest_framework.viewsets import ViewSet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT


class MTRouterViewSet(ViewSet):
    """
    ViewSet for managing MT (Mobile Terminated) Routes via telnet commands.

    Supports listing, retrieving, creating, flushing, and deleting MT routes.
    """
    lookup_field = 'order'

    def _list(self, telnet):
        """
        List all MT routers and return them as a Python dictionary.

        :param telnet: The telnet connection to the Jasmin server.
        :return: A dict with a 'mtrouters' key containing a list of routes.
        """
        telnet.sendline('mtrouter -l')
        telnet.expect([rf'(.+)\n{STANDARD_PROMPT}'])
        result = telnet.match.group(0).decode('utf-8').strip().replace("\r", '').split("\n")

        if len(result) < 3:
            return {'mtrouters': []}

        # Clean and parse the results
        cleaned_lines = [
            line.replace(', ', ',').replace('(!)', '')
            for line in result[2:-2] if line
        ]
        routers = split_cols(cleaned_lines)
        return {
            'mtrouters': [
                {
                    'order': router[0].strip().lstrip('#'),
                    'type': router[1],
                    'rate': router[2],
                    'connectors': [c.strip() for c in router[3].split(',')],
                    'filters': (
                        [f.strip() for f in ' '.join(router[4:]).split(',')]
                        if len(router) > 4 else []
                    )
                } for router in routers
            ]
        }

    def list(self, request):
        """
        List all MT routers.

        No parameters required.
        """
        try:
            routers = self._list(request.telnet)
            return JsonResponse(routers)
        except Exception as e:
            logger.error(f"Error listing MT routers: {e}")
            raise UnknownError("Error listing MT routers")

    def get_router(self, telnet, order):
        """
        Retrieve data for a single MT router identified by 'order'.

        :param telnet: Telnet connection.
        :param order: The order identifier of the MT router.
        :return: A dict with the 'mtrouter' key representing the router data.
        :raises ObjectNotFoundError: If no router is found with the given order.
        """
        morouters = self._list(telnet)['mtrouters']
        router = next((m for m in morouters if m['order'] == order), None)
        if router is None:
            raise ObjectNotFoundError(f'No MTRouter with order: {order}')
        return {'mtrouter': router}

    def retrieve(self, request, order):
        """
        Retrieve details for a single MT router by its order (integer/string).

        :param order: The router's order identifier.
        """
        try:
            router = self.get_router(request.telnet, order)
            return JsonResponse(router)
        except ObjectNotFoundError as e:
            logger.error(f"Error retrieving MT router: {e}")
            raise UnknownError(detail=str(e))

    @action(detail=False, methods=['delete'])
    def flush(self, request):
        """
        Flush the entire MT routing table.

        After flushing, persist changes and sync configurations if applicable.
        """
        telnet = request.telnet
        telnet.sendline('mtrouter -f')
        telnet.expect([rf'(.+)\n{STANDARD_PROMPT}'])
        telnet.sendline('persist\n')
        telnet.expect(rf'.*{STANDARD_PROMPT}')

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(request.telnet_list)

        return JsonResponse({'mtrouters': []})

    def create(self, request):
        """
        Create a new MT Router.

        Required parameters:
        - type: One of DefaultRoute, StaticMTRoute, RandomRoundrobinMTRoute
        - order: Router order, used to identify the router
        - rate: Router rate (float), may be zero for free

        Optional parameters:
        - smppconnectors: List of SMPP connector IDs
        - httpconnectors: List of HTTP connector IDs
        - filters: List of filters (required except for DefaultRoute)

        Raises:
            MissingKeyError: If required parameters are missing.
            MutipleValuesRequiredKeyError: If multiple connectors are required but not provided.
            JasminSyntaxError: If there's a syntax error in the provided parameters.
            UnknownError: For other unforeseen errors.
        """
        telnet = request.telnet
        data = request.data

        # Validate required parameters
        try:
            rtype = data['type'].lower()
            order = data['order']
            rate = float(data['rate'])
        except KeyError as e:
            raise MissingKeyError(f'Missing parameter: {e.args[0]} is required')
        except ValueError:
            raise JasminSyntaxError('Invalid rate value; must be a float')

        telnet.sendline('mtrouter -a')
        telnet.expect(rf'Adding a new MT Route(.+)\n{INTERACTIVE_PROMPT}')

        ikeys = OrderedDict({'type': rtype})

        if rtype != 'defaultroute':
            try:
                filters = data['filters'].split(',')
            except (MultiValueDictKeyError, AttributeError):
                raise MissingKeyError(f'{rtype} router requires filters')
            ikeys['filters'] = ';'.join([f.strip() for f in filters])
            ikeys['order'] = order

        # Handle connectors
        smppconnectors = data.get('smppconnectors', '')
        httpconnectors = data.get('httpconnectors', '')
        connectors = [
                         f'smppc({c.strip()})' for c in smppconnectors.split(',') if c.strip()
                     ] + [
                         f'http({c.strip()})' for c in httpconnectors.split(',') if c.strip()
                     ]

        if rtype == 'randomroundrobinmtroute':
            if len(connectors) < 2:
                raise MultipleValuesRequiredKeyError(
                    'RandomRoundrobinMTRoute requires at least two connectors'
                )
            ikeys['connectors'] = ';'.join(connectors)
        else:
            if len(connectors) != 1:
                raise MissingKeyError('One and only one connector is required for this router type')
            ikeys['connector'] = connectors[0]

        # Set the rate
        ikeys['rate'] = rate

        logger.info(f"Setting keys for MT router: {ikeys}")
        set_ikeys(telnet, ikeys)

        # Persist changes
        telnet.sendline('persist\n')
        telnet.expect(rf'.*{STANDARD_PROMPT}')

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(request.telnet_list)

        return JsonResponse({'mtrouter': self.get_router(telnet, order)})

    def simple_mtrouter_action(self, telnet, telnet_list, action, order, return_mtroute=True):
        """
        Perform a simple action (e.g., remove) on a MT router.

        :param telnet: Telnet connection.
        :param telnet_list: List of telnet connections for syncing.
        :param action: The action character (e.g., 'r' for remove).
        :param order: The order identifier of the router.
        :param return_mtroute: If True, return the updated router data after the action.
        :return: JsonResponse with the result.
        :raises:
            UnknownError: If the router is not found.
            JasminError: For other errors returned by Jasmin.
        """
        telnet.sendline(f'mtrouter -{action} {order}')
        matched_index = telnet.expect([
            rf'.+Successfully(.+){STANDARD_PROMPT}',
            rf'.+Unknown MT Route: (.+){STANDARD_PROMPT}',
            rf'.+(.*){STANDARD_PROMPT}',
        ])

        if matched_index == 0:
            # Action succeeded
            telnet.sendline('persist\n')
            telnet.expect(rf'.*{STANDARD_PROMPT}')

            if return_mtroute and (settings.JASMIN_DOCKER or settings.JASMIN_K8S):
                sync_conf_instances(telnet_list)
                return JsonResponse({'mtrouter': self.get_router(telnet, order)})
            elif not return_mtroute and (settings.JASMIN_DOCKER or settings.JASMIN_K8S):
                sync_conf_instances(telnet_list)
                return JsonResponse({'order': order})
            else:
                if return_mtroute:
                    return JsonResponse({'mtrouter': self.get_router(telnet, order)})
                else:
                    return JsonResponse({'order': order})

        elif matched_index == 1:
            # Router not found
            raise UnknownError(detail=f'No router: {order}')
        else:
            # Some other Jasmin-related error
            error_message = telnet.match.group(1).decode('utf-8').strip() if telnet.match.group(1).decode('utf-8') else 'Unknown error'
            raise JasminError(error_message)

    def destroy(self, request, order):
        """
        Delete an MT router by its order identifier.

        HTTP response codes:
        - 200: Successful deletion
        - 404: Nonexistent router
        - 400: Other errors
        """
        return self.simple_mtrouter_action(
            telnet=request.telnet,
            telnet_list=request.telnet_list,
            action='r',
            order=order,
            return_mtroute=False
        )
