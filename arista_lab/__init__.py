__version__ = "0.1.0"

import ssl
from pyeapi.eapilib import HttpsEapiConnection  # type: ignore[import-untyped]


class LabEapiConnection(HttpsEapiConnection):
    """
    https://arista.my.site.com/AristaCommunity/s/article/Python-3-10-and-SSLV3-ALERT-HANDSHAKE-FAILURE-error
    """

    def __init__(self, **kwargs):
        # Use TLSv1.2
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # Using the EOS default ciphers
        context.set_ciphers(
            "AES256-SHA:DHE-RSA-AES256-SHA:AES128-SHA:DHE-RSA-AES128-SHA"
        )

        if "context" in kwargs:
            del kwargs["context"]

        super(LabEapiConnection, self).__init__(**kwargs, context=context)
