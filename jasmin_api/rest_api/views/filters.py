import logging
import traceback
from collections import OrderedDict

from django.conf import settings
from django.http import JsonResponse
from django.utils.datastructures import MultiValueDictKeyError

from rest_framework.viewsets import ViewSet

from rest_api.tools import set_ikeys, split_cols, sync_conf_instances
from rest_api.exceptions import (
    JasminSyntaxError, JasminError, UnknownError,
    MissingKeyError, MutipleValuesRequiredKeyError,
    ObjectNotFoundError
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT


class FiltersViewSet(ViewSet):
    """
    Viewset for managing Jasmin Filters through a telnet interface.

    Supports listing, retrieving, creating, and deleting filters.
    """
    lookup_field = 'fid'

    def _list(self, telnet):
        """
        List all filters via the telnet connection and return them as a Python dict.
        """
        telnet.sendline('filter -l')
        telnet.expect([r'(.+)\n' + STANDARD_PROMPT])
        result = telnet.match.group(0).strip().replace("\r", '').split("\n")

        # If there are fewer than 3 lines, it means no filters are listed
        if len(result) < 3:
            return {'filters': []}

        # Clean and parse results
        parsed_lines = [
            l.replace(', ', ',').replace('(!)', '')
            for l in result[2:-2] if l
        ]
        filters = split_cols(parsed_lines)
        return {
            'filters': [
                {
                    'fid': f[0].strip().lstrip('#'),
                    'type': f[1],
                    'routes': f"{f[2]} {f[3]}",
                    'description': ' '.join(f[4:])
                }
                for f in filters
            ]
        }

    def list(self, request):
        """
        List all filters. No parameters required.
        """
        try:
            filters = self._list(request.telnet)
            return JsonResponse(filters)
        except Exception as e:
            logger.error("Error listing filters: %s", e)
            raise UnknownError("Error listing filters")

    def get_filter(self, telnet, fid):
        """
        Return data for a single filter identified by 'fid' as a Python dict.

        Raises ObjectNotFoundError if the filter does not exist.
        """
        filters = self._list(telnet)['filters']
        fil = next((m for m in filters if m['fid'] == fid), None)
        if fil is None:
            raise ObjectNotFoundError(f"No Filter with fid: {fid}")
        return {'filter': fil}

    def retrieve(self, request, fid):
        """
        Retrieve details for one filter by fid (string).
        """
        try:
            return JsonResponse(self.get_filter(request.telnet, fid))
        except ObjectNotFoundError as e:
            raise UnknownError(detail=str(e))

    def create(self, request):
        """
        Create a filter. Required parameters: type, fid, and parameter (if type != transparentfilter)

        Filter types:
        TransparentFilter, ConnectorFilter, UserFilter, GroupFilter, SourceAddrFilter,
        DestinationAddrFilter, ShortMessageFilter, DateIntervalFilter,
        TimeIntervalFilter, TagFilter, EvalPyFilter.
        """
        telnet = request.telnet
        data = request.data

        # Validate required keys: type and fid
        try:
            ftype = data['type'].lower()
            fid = data['fid']
        except KeyError:
            raise MissingKeyError('Missing parameter: type or fid is required')

        telnet.sendline('filter -a')
        telnet.expect(r'Adding a new Filter(.+)\n' + INTERACTIVE_PROMPT)

        # Construct interactive keys
        ikeys = OrderedDict({'type': ftype, 'fid': fid})

        # If type is not transparentfilter, parameter is required
        if ftype != 'transparentfilter':
            try:
                parameter = data['parameter']
            except MultiValueDictKeyError:
                raise MissingKeyError(f'{ftype} filter requires parameter')

            # Map parameter to correct key based on filter type
            type_param_map = {
                'connectorfilter': 'cid',
                'userfilter': 'uid',
                'groupfilter': 'gid',
                'sourceaddrfilter': 'source_addr',
                'destinationaddrfilter': 'destination_addr',
                'shortmessagefilter': 'short_message',
                'dateintervalfilter': 'dateInterval',
                'timeintervalfilter': 'timeInterval',
                'tagfilter': 'tag',
                'evalpyfilter': 'pyCode'
            }

            if ftype in type_param_map:
                ikeys[type_param_map[ftype]] = parameter
            else:
                # If a new filter type is introduced without updating this map
                raise JasminError(f"Unsupported filter type: {ftype}")

        set_ikeys(telnet, ikeys)
        telnet.sendline('persist\n')
        telnet.expect(r'.*' + STANDARD_PROMPT)

        # Sync instances if running under Docker/K8s
        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(request.telnet_list)

        # Return created filter details
        return JsonResponse({'filter': self.get_filter(telnet, fid)})

    def simple_filter_action(self, telnet, telnet_list, action, fid, return_filter=True):
        """
        Perform a simple filter action (e.g., remove) and return the appropriate response.

        :param telnet: The telnet connection object.
        :param telnet_list: List of telnet connections for synchronization.
        :param action: The action to perform on the filter ('r' for remove, for example).
        :param fid: Filter ID to act upon.
        :param return_filter: If True, return the filter data after the action.
        """
        telnet.sendline(f'filter -{action} {fid}')
        matched_index = telnet.expect([
            r'.+Successfully(.+)' + STANDARD_PROMPT,
            r'.+Unknown Filter: (.+)' + STANDARD_PROMPT,
            r'.+(.*)' + STANDARD_PROMPT,
            ])

        if matched_index == 0:
            # Action succeeded
            telnet.sendline('persist\n')
            telnet.expect(r'.*' + STANDARD_PROMPT)

            # Sync configurations across instances if needed
            if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
                sync_conf_instances(telnet_list)

            if return_filter:
                return JsonResponse({'filter': self.get_filter(telnet, fid)})
            else:
                return JsonResponse({'fid': fid})

        elif matched_index == 1:
            # Unknown Filter
            raise UnknownError(detail=f'No filter: {fid}')
        else:
            # Some other Jasmin error
            raise JasminError(telnet.match.group(1))

    def destroy(self, request, fid):
        """
        Delete a filter by fid.

        HTTP response codes:
        - 200: successful deletion
        - 404: filter not found
        - 400: other error
        """
        return self.simple_filter_action(
            request.telnet, request.telnet_list, 'r', fid, return_filter=False
        )
