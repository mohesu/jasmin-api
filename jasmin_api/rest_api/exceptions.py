import logging
import traceback

logging.basicConfig(level=logging.INFO)

from rest_framework.exceptions import APIException





class TelnetUnexpectedResponse(APIException):
    """
    Raised when Jasmin returns an unexpected response.
    """
    status_code = 500
    default_detail = "Unexpected response from Jasmin."


class TelnetConnectionTimeout(APIException):
    """
    Raised when the Telnet connection to JCLI times out.
    """
    status_code = 500
    default_detail = "Connection to JCLI timed out."


class TelnetLoginFailed(APIException):
    """
    Raised when Jasmin login fails due to incorrect credentials or other reasons.
    """
    status_code = 403
    default_detail = "Jasmin login failed."


class CanNotModifyError(APIException):
    """
    Raised when an attempt to modify an unmodifiable key is made.
    """
    status_code = 400
    default_detail = "Cannot modify the specified key."


class JasminSyntaxError(APIException):
    """
    Raised for syntax errors in Jasmin commands.
    """
    status_code = 400
    default_detail = "Syntax error in Jasmin command."


class JasminError(APIException):
    """
    Raised for general Jasmin errors.
    """
    status_code = 400
    default_detail = "An error occurred in Jasmin."


class UnknownError(APIException):
    """
    Raised when an object or operation is unknown to Jasmin.
    """
    status_code = 404
    default_detail = "Object or operation not known."


class MissingKeyError(APIException):
    """
    Raised when a mandatory key is missing in the request.
    """
    status_code = 400
    default_detail = "A mandatory key is missing."


class MultipleValuesRequiredKeyError(APIException):
    """
    Raised when multiple values are required for a specific key.
    """
    status_code = 400
    default_detail = "Multiple values are required for this key."


class ActionFailed(APIException):
    """
    Raised when an action fails to execute.
    """
    status_code = 400
    default_detail = "Action failed."


class ObjectNotFoundError(APIException):
    """
    Raised when a requested object is not found in Jasmin.
    """
    status_code = 404
    default_detail = "Object not found."
