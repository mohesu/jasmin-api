import logging

logging.basicConfig(level=logging.INFO)

import traceback

from .exceptions import (CanNotModifyError, JasminSyntaxError,
                         UnknownError)
from django.conf import settings

STANDARD_PROMPT = settings.STANDARD_PROMPT
INTERACTIVE_PROMPT = settings.INTERACTIVE_PROMPT


def set_ikeys(telnet, keys2vals):
    """
    Set multiple keys for interactive command in Jasmin.
    """
    for key, val in keys2vals.items():
        logging.info(f"Setting {key} = {val}")
        telnet.sendline(f"{key} {val}")
        matched_index = telnet.expect([
            r'.*(Unknown .*)' + INTERACTIVE_PROMPT,
            r'(.*) can not be modified.*' + INTERACTIVE_PROMPT,
            r'(.*)' + INTERACTIVE_PROMPT,
            r'.*(Unknown SMPPClientConfig key:.*)' + INTERACTIVE_PROMPT,
            r'.*(Error:.*)' + STANDARD_PROMPT,
        ])
        result = telnet.match.group(1).strip()
        if matched_index == 0:
            raise UnknownError(result)
        if matched_index == 1:
            raise CanNotModifyError(result)
        if matched_index in {3, 4}:
            raise JasminSyntaxError(detail=" ".join(result.split()))

    telnet.sendline('ok')
    ok_index = telnet.expect([
        r'ok(.* syntax is invalid).*' + INTERACTIVE_PROMPT,
        r'.*' + STANDARD_PROMPT,
    ])
    if ok_index == 0:
        # Remove whitespace and return error
        raise JasminSyntaxError(" ".join(telnet.match.group(1).split()))

    return


def split_cols(lines):
    """
    Split columns into lists, skipping blank and non-data lines.
    """
    parsed = []
    for line in lines:
        raw_split = line.split()
        # Include fields only if the line starts with `#`
        fields = [s for s in raw_split if raw_split and raw_split[0][0] == '#']
        if fields:  # Skip empty results
            parsed.append(fields)
    return parsed


def sync_conf_instances(telnet_list):
    """
    Sync configuration across instances of Jasmin in Docker.
    """
    for telnet in telnet_list:
        try:
            telnet.sendline('load\n')
            telnet.expect(r'.*' + STANDARD_PROMPT)
        except Exception as e:
            logging.info(f"Error syncing configuration: {e}")
            traceback.print_exc()
    return
