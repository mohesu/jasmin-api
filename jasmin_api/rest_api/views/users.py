import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils.datastructures import MultiValueDictKeyError

from rest_api.exceptions import (
    JasminSyntaxError, JasminError,
    UnknownError, MissingKeyError, ObjectNotFoundError
)
from rest_api.tools import set_ikeys, sync_conf_instances

from rest_framework.decorators import action, parser_classes  # Replaced deprecated decorators
from rest_framework.parsers import JSONParser
from rest_framework.viewsets import ViewSet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT


class UserViewSet(ViewSet):
    """
    ViewSet for managing Jasmin users (*not* Django auth users).

    Supports listing, retrieving, creating, updating, enabling, disabling,
    unbinding, banning, and deleting Jasmin users via telnet commands.
    """
    lookup_field = 'uid'

    def get_user(self, telnet, uid, silent=False):
        """
        Retrieve a single user's data.

        :param telnet: Telnet connection to Jasmin server.
        :param uid: User identifier.
        :param silent: If True, suppress Http404 exception if user not found.
        :return: Dictionary containing user data.
        :raises ObjectNotFoundError: If user is not found and silent=False.
        """
        telnet.sendline(f'user -s {uid}')
        matched_index = telnet.expect([
            rf'.+Unknown User:.*{STANDARD_PROMPT}',
            rf'.+Usage: user.*{STANDARD_PROMPT}',
            rf'(.+)\n{STANDARD_PROMPT}',
        ])

        if matched_index != 2:
            if silent:
                return None
            raise ObjectNotFoundError(f'Unknown user: {uid}')

        result = telnet.match.group(1)
        user = {}
        # Skip the first line if it's a header or irrelevant
        for line in [l for l in result.splitlines() if l][1:]:
            parts = [x for x in line.split() if x]
            if len(parts) == 2:
                user[parts[0]] = parts[1]
            elif len(parts) == 4:
                # Handling nested attributes
                if parts[0] not in user:
                    user[parts[0]] = {}
                if parts[1] not in user[parts[0]]:
                    user[parts[0]][parts[1]] = {}
                user[parts[0]][parts[1]][parts[2]] = parts[3]
            # Assumes each line has either 2 or 4 elements
        return user

    def retrieve(self, request, uid):
        """
        Retrieve data for one user.

        :param uid: User identifier.
        :return: JsonResponse containing user data.
        """
        try:
            user = self.get_user(request.telnet, uid)
            return JsonResponse({'user': user})
        except ObjectNotFoundError as e:
            logger.error(f"Error retrieving user: {e}")
            raise UnknownError(detail=str(e))

    def list(self, request):
        """
        List all users.

        No parameters required.

        :return: JsonResponse containing a list of users.
        """
        telnet = request.telnet
        telnet.sendline('user -l')
        telnet.expect([rf'(.+)\n{STANDARD_PROMPT}'])
        result = telnet.match.group(0).strip()
        if len(result) < 3:
            return JsonResponse({'users': []})

        results = [l for l in result.splitlines() if l]
        # Extract UIDs, removing the '#' prefix and handling disabled users (starting with '!')
        annotated_uids = [u.split(None, 1)[0][1:] for u in results[2:-2]]
        users = []
        for auid in annotated_uids:
            if auid.startswith('!'):
                udata = self.get_user(telnet, auid[1:], silent=True)
                if udata:
                    udata['status'] = 'disabled'
            else:
                udata = self.get_user(telnet, auid, silent=True)
                if udata:
                    udata['status'] = 'enabled'
            if udata:
                users.append(udata)
        return JsonResponse({'users': users})

    def create(self, request):
        """
        Create a new user.

        Required parameters: uid, gid, username, password.

        :param request: DRF Request object containing user data.
        :return: JsonResponse containing the created user's data.
        :raises MissingKeyError: If required parameters are missing.
        """
        telnet = request.telnet
        data = request.data
        try:
            uid = data['uid']
            gid = data['gid']
            username = data['username']
            password = data['password']
        except KeyError as e:
            raise MissingKeyError(f'Missing parameter: {e.args[0]} is required')

        telnet.sendline('user -a')
        telnet.expect(rf'Adding a new User(.+)\n{INTERACTIVE_PROMPT}')
        user_data = {
            'uid': uid,
            'gid': gid,
            'username': username,
            'password': password
        }
        set_ikeys(telnet, user_data)

        telnet.sendline('persist\n')
        telnet.expect(rf'.*{STANDARD_PROMPT}')

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(getattr(request, 'telnet_list', []))

        user = self.get_user(telnet, uid)
        return JsonResponse({'user': user})

    @action(detail=True, methods=['put'], url_path='enable')
    def enable(self, request, uid):
        """
        Enable a user.

        :param uid: User identifier.
        :return: JsonResponse indicating the user's new status.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='e',
            uid=uid
        )

    @action(detail=True, methods=['put'], url_path='disable')
    def disable(self, request, uid):
        """
        Disable a user.

        :param uid: User identifier.
        :return: JsonResponse indicating the user's new status.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='d',
            uid=uid
        )

    @action(detail=True, methods=['put'], url_path='smpp-unbind')
    def smpp_unbind(self, request, uid):
        """
        Unbind user from SMPP server.

        :param uid: User identifier.
        :return: JsonResponse indicating the result.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='-smpp-unbind',
            uid=uid
        )

    @action(detail=True, methods=['put'], url_path='smpp-ban')
    def smpp_ban(self, request, uid):
        """
        Unbind and ban user from SMPP server.

        :param uid: User identifier.
        :return: JsonResponse indicating the result.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='-smpp-ban',
            uid=uid
        )

    @action(detail=True, methods=['patch'], parser_classes=[JSONParser], url_path='partial-update')
    def partial_update(self, request, uid):
        """
        Update some user attributes.

        JSON requests only. The updates parameter is a list of lists.
        Each inner list contains valid arguments for user update.

        Example:
            [
                ["gid", "newgroup"],
                ["mt_messaging_cred", "authorization", "smpps_send", "False"]
            ]

        :param uid: User identifier.
        :param request: DRF Request object containing updates.
        :return: JsonResponse with updated user data.
        :raises:
            JasminSyntaxError: If updates are malformed.
            UnknownError: If the user does not exist.
            JasminError: For other errors returned by Jasmin.
        """
        telnet = request.telnet
        telnet.sendline(f'user -u {uid}')
        matched_index = telnet.expect([
            rf'.*Updating User(.*){INTERACTIVE_PROMPT}',
            rf'.*Unknown User: (.*){STANDARD_PROMPT}',
            rf'.+(.*)(' + INTERACTIVE_PROMPT + '|' + STANDARD_PROMPT + ')',
            ])

        if matched_index == 1:
            raise UnknownError(detail=f'Unknown user: {uid}')
        if matched_index != 0:
            error_message = telnet.match.group(0).strip()
            raise JasminError(detail=error_message)

        updates = request.data
        if not isinstance(updates, list) or not updates:
            raise JasminSyntaxError('Updates should be a non-empty list of lists.')

        for update in updates:
            if not isinstance(update, list) or not update:
                raise JasminSyntaxError(f'Invalid update format: {update}')
            command = " ".join(update)
            telnet.sendline(f"{command}\n")
            matched_index = telnet.expect([
                rf'.*(Unknown User key:.*){INTERACTIVE_PROMPT}',
                rf'.*(Error:.*){STANDARD_PROMPT}',
                rf'.*{INTERACTIVE_PROMPT}',
                rf'.+(.*)(' + INTERACTIVE_PROMPT + '|' + STANDARD_PROMPT + ')',
                ])
            if matched_index != 2:
                error_detail = telnet.match.group(1).strip() if telnet.match.group(1) else 'Unknown error'
                raise JasminSyntaxError(detail=error_detail)

        telnet.sendline('ok\n')
        ok_index = telnet.expect([
            rf'.*(Error:.*){STANDARD_PROMPT}',
            rf'.*{INTERACTIVE_PROMPT}',
        ])
        if ok_index == 0:
            error_detail = telnet.match.group(1).strip()
            raise JasminSyntaxError(detail=error_detail)

        telnet.sendline('persist\n')
        telnet.expect(rf'.*{STANDARD_PROMPT}')

        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(getattr(request, 'telnet_list', []))

        user = self.get_user(telnet, uid)
        return JsonResponse({'user': user})

    def simple_user_action(self, telnet, telnet_list, action, uid, return_user=True):
        """
        Perform a simple action (e.g., remove, enable, disable, unbind, ban) on a user.

        :param telnet: Telnet connection.
        :param telnet_list: List of telnet connections for syncing.
        :param action: The action character (e.g., 'r' for remove, 'e' for enable).
        :param uid: User identifier.
        :param return_user: If True, return the updated user data after the action.
        :return: JsonResponse with the result.
        :raises:
            UnknownError: If the user does not exist.
            JasminError: If the action fails.
        """
        telnet.sendline(f'user -{action} {uid}')
        matched_index = telnet.expect([
            rf'.+Successfully(.+){STANDARD_PROMPT}',
            rf'.+Unknown User: (.+){STANDARD_PROMPT}',
            rf'.+(.*){STANDARD_PROMPT}',
        ])

        if matched_index == 0:
            # Action succeeded
            telnet.sendline('persist\n')
            telnet.expect(rf'.*{STANDARD_PROMPT}')
            if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
                sync_conf_instances(telnet_list)
            if return_user:
                telnet.expect(rf'.*{STANDARD_PROMPT}')
                user = self.get_user(telnet, uid)
                return JsonResponse({'user': user})
            else:
                return JsonResponse({'uid': uid})
        elif matched_index == 1:
            # User not found
            raise UnknownError(detail=f'No user: {uid}')
        else:
            # Some other error
            error_message = telnet.match.group(1).strip() if telnet.match.group(1) else 'Unknown error'
            raise JasminError(error_message)

    @action(detail=True, methods=['put'], url_path='enable')
    def enable(self, request, uid):
        """
        Enable a user.

        :param uid: User identifier.
        :return: JsonResponse indicating the user's new status.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='e',
            uid=uid
        )

    @action(detail=True, methods=['put'], url_path='disable')
    def disable(self, request, uid):
        """
        Disable a user.

        :param uid: User identifier.
        :return: JsonResponse indicating the user's new status.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='d',
            uid=uid
        )

    @action(detail=True, methods=['put'], url_path='smpp-unbind')
    def smpp_unbind(self, request, uid):
        """
        Unbind user from SMPP server.

        :param uid: User identifier.
        :return: JsonResponse indicating the result.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='-smpp-unbind',
            uid=uid
        )

    @action(detail=True, methods=['put'], url_path='smpp-ban')
    def smpp_ban(self, request, uid):
        """
        Unbind and ban user from SMPP server.

        :param uid: User identifier.
        :return: JsonResponse indicating the result.
        """
        return self.simple_user_action(
            telnet=request.telnet,
            telnet_list=getattr(request, 'telnet_list', []),
            action='-smpp-ban',
            uid=uid
        )
