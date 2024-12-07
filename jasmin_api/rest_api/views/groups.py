import logging
import traceback

logging.basicConfig(level=logging.INFO)

from django.conf import settings

from django.http import JsonResponse

from rest_api.exceptions import MissingKeyError, ActionFailed, ObjectNotFoundError

from rest_api.tools import set_ikeys, sync_conf_instances

from rest_framework.decorators import action

from rest_framework.viewsets import ViewSet






STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT

class GroupViewSet(ViewSet):
    "ViewSet for managing *Jasmin* user groups (*not* Django auth groups)"
    lookup_field = 'gid'

    def list(self, request):
        "List groups. No request parameters provided or required."
        telnet = request.telnet
        telnet.sendline('group -l')
        telnet.expect([r'(.+)\n' + STANDARD_PROMPT])
        result = telnet.match.group(0).strip().replace("\r", '').split("\n")
        if len(result) < 3:
            return JsonResponse({'groups': []})
        groups = result[2:-2]
        return JsonResponse(
            {
                'groups':
                    [
                        {
                            'name': g.strip().lstrip('!#'), 'status': (
                                'disabled' if g[1] == '!' else 'enabled'
                            )
                        } for g in groups
                    ]
            }
        )

    def create(self, request):
        """Create a group.
        One POST parameter required, the group identifier (a string)
        ---
        # YAML
        omit_serializer: true
        parameters:
        - name: gid
          description: Group identifier
          required: true
          type: string
          paramType: form
        """
        telnet = request.telnet
        telnet.sendline('group -a')
        telnet.expect(r'Adding a new Group(.+)\n' + INTERACTIVE_PROMPT)
        if not 'gid' in request.data:
            raise MissingKeyError('Missing gid (group identifier)')

        set_ikeys(telnet, {"gid": request.data["gid"]})

        telnet.sendline('persist')
        telnet.expect(r'.*' + STANDARD_PROMPT)
        if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
            sync_conf_instances(request.telnet_list)
        return JsonResponse({'name': request.data["gid"]})

    def simple_group_action(self, telnet, telnet_list, action, gid):
        telnet.sendline('group -%s %s' % (action, gid))
        matched_index = telnet.expect([
            r'.+Successfully(.+)' + STANDARD_PROMPT,
            r'.+Unknown Group: (.+)' + STANDARD_PROMPT,
            r'.+(.*)' + STANDARD_PROMPT,
        ])
        if matched_index == 0:
            telnet.sendline('persist\n')
            if settings.JASMIN_DOCKER or settings.JASMIN_K8S:
                sync_conf_instances(telnet_list)
            return JsonResponse({'name': gid})
        elif matched_index == 1:
            raise ObjectNotFoundError('Unknown group: %s' % gid)
        else:
            raise ActionFailed(telnet.match.group(1))

    def destroy(self, request, gid):
        """Delete a group. One parameter required, the group identifier (a string)

        HTTP codes indicate result as follows

        - 200: successful deletion
        - 404: nonexistent group
        - 400: other error
        """
        return self.simple_group_action(request.telnet, request.telnet_list, 'r', gid)

    @action(detail=True, methods=['put'])
    def enable(self, request, gid):
        """Enable a group. One parameter required, the group identifier (a string)

        HTTP codes indicate result as follows

        - 200: successful deletion
        - 404: nonexistent group
        - 400: other error
        """
        return self.simple_group_action(request.telnet, request.telnet_list, 'e', gid)


    @action(detail=True, methods=['put'])
    def disable(self, request, gid):
        """Disable a group.

        One parameter required, the group identifier (a string)

        HTTP codes indicate result as follows

        - 200: successful deletion
        - 404: nonexistent group
        - 400: other error
        """
        return self.simple_group_action(request.telnet, request.telnet_list, 'd', gid)
