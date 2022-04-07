import sys
from twisted.internet import ssl, protocol, task, defer
from twisted.python import log


class Echo(protocol.Protocol):

    def dataReceived(self, data):
        self.transport.write(data)

certPEMData = """-----BEGIN CERTIFICATE-----
MIIC+zCCAeOgAwIBAgIJAIFX9UG7/D01MA0GCSqGSIb3DQEBCwUAMBQxEjAQBgNV
BAMMCWxvY2FsaG9zdDAeFw0xNTA2MDQxNjAxMDhaFw0xNTA3MDQxNjAxMDhaMBQx
EjAQBgNVBAMMCWxvY2FsaG9zdDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoC
ggEBAJ3q7AQ6r+/MsL9bwpg2eXD+AJAIH+RCI/LZJQ8FvhIBi19hLHnt29I5hXr6
786hJrY5ZIuPvU+8vcxlfGigo5SYFBxD8m7nWfdMVXDD4CKhiVLb453yUmIFdD2w
v+F8RWBDWMXJ6dOLfaC3t12XlIMW9hyX2b7tf7e3v6/++oqfq3V02B12WAKMB48B
3+86VkzY/3ju/ri0b9tF25nB2mjhsGL3Z5z15pBSY9ExSgbpcX/X4K+YiAerdg5+
UjpKOA5OfMqi8bn1xXxl/cjqrVf87o1IbSbQd/RgpGfpIlhx50dESriPgwU+BbfD
DfMbCfGh+m6MUju0cUCG0d08O9ECAwEAAaNQME4wHQYDVR0OBBYEFFOvxiLj5UMW
dCo3bajBOegHKibeMB8GA1UdIwQYMBaAFFOvxiLj5UMWdCo3bajBOegHKibeMAwG
A1UdEwQFMAMBAf8wDQYJKoZIhvcNAQELBQADggEBAJU1pHgby0DBiEzNW73U+Wvp
4bGC9aisO2u0drD79U2QogYcX9TD/f7PoObxwxPZAgOvSpqipHMPoylgbGEaXj9v
pD6Cf5vub64/35IhEUfw8/UENU/9BSkvEkL0gD8jTiavYKAg5z6VYnzvDaLwJgVu
9kplXtRmwNYiYeX8CBnTVa5d9MGt7YaF+46edlCi3sX5L1jne4ZOY9hwIBjYnFhC
7l4RLj0fxHSsKLRVcLZH5TKB4E3kdWeaLDZsKqn4MQObmW4YJhnZzZDqzcdtoqtO
ogaJzMB1bZbvAZBmfwKLALINYqgRBzkUh24hdCtVuW7KVhHO1SE5ndfqLOlhyD4=
-----END CERTIFICATE-----
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCd6uwEOq/vzLC/
W8KYNnlw/gCQCB/kQiPy2SUPBb4SAYtfYSx57dvSOYV6+u/OoSa2OWSLj71PvL3M
ZXxooKOUmBQcQ/Ju51n3TFVww+AioYlS2+Od8lJiBXQ9sL/hfEVgQ1jFyenTi32g
t7ddl5SDFvYcl9m+7X+3t7+v/vqKn6t1dNgddlgCjAePAd/vOlZM2P947v64tG/b
RduZwdpo4bBi92ec9eaQUmPRMUoG6XF/1+CvmIgHq3YOflI6SjgOTnzKovG59cV8
Zf3I6q1X/O6NSG0m0Hf0YKRn6SJYcedHREq4j4MFPgW3ww3zGwnxofpujFI7tHFA
htHdPDvRAgMBAAECggEAJXbiX2585uss03k1hV8HGKNqBsGmr0Rxut+BRzsZiLQN
GKe5IYQorosu+6ok0mSxBnI/REzpoM0qSh+ZkEjsBgi+XKZSEbWZRm45pvMRbaXd
Kmc4bPRcTxz0It6X5yrQWrIfkW0BqEpjl4l+WxnnBeKgqM/tvLojnrZdJ6faUKCJ
YTFoUN/A+/n32YfTKXYmbCA5AHBh3utQwQ3nhVWV/36EEgrXelkFyjZPYbSC3FDD
M8I5JqyGIiLrMWtgtQZYVBb9LbL6hWxdt5jCqDWj0q5GWKzk22T4svZtehEuem3m
6fjnoqrd1aOEbW9C9rSvJSQ+UfvgkSQNNfju7hrpcQKBgQDOffB2s/P+HcUGxPJ8
DaiAs0OVTbV5bYi8olx0p1FEl9xeiK3k6qw3izdan5fyHCY3tfh1t+uKy/185IJU
XIV2ipJneOINHEhtqigl+IuXPm8VppJ+dssMwWtztQhtGKJzSweRTYX+ram4txXL
O05eD8XrD3OWBrsShdXxNT6FJwKBgQDDx5cxGUo1FQEpK4oC2OuaruEBC2QpCNRf
1jV2LGD8vR9XgeuRftetQRpZ32gi4rvbd7icaftqc7WoNz7v1NO/9a9JEw04x3N3
PMNfAnyGhL2USrMTPEYoe7+Bsvc5LKOAgDmJWNGG99yU6B2tk8eR1lgVl2/kfzBT
K5tCrC0CRwKBgQCuhJgf6tVTNxvXLcr296ArLdb3r9apit6e9uYHHYY839A7AW9e
4susofelmu6TjCDswtn7u/bRtrhFvuc7n3qZBmLYGr2KcRXxwXbvKJHpwLWn6cE0
KvhPjoVfJGi7s69Qm+AIeSm/ZkzkNbCwtC32p4QRt1xsNsIS1JRNqT9uzwKBgQCK
cnV3kiPI/+6PN6vkMZQDEhIpk+2jmwvcLfYmeGGpuPAWCNkWTbWlXnmM/pB8wwwH
ulUBv2y8rdDTgSXvofiQMeRf76oU8e60bnLWmEKJOgt6d4zFWIVgkYou5OkxNGD3
OTX266lYIaWKY87A9dVWS1aFBk9pLYx19EtaTbmSdwKBgHcygmI/WglOSuRTg7sE
vC1FmFkM82981HhZVtm25sDeNvFdr5VTy9R3BeUXMwh32VlQt0LBBIp/3AE/mz18
4KEQ21PukryWv/JVgva+B02F5ON30V2uJHM5cGjFtmxp536pmrC4mdWwAPUWa8lW
ZRl2W+adiPa/TmRMU491COsD
-----END PRIVATE KEY-----"""


def main(reactor):
    log.startLogging(sys.stdout)
    certificate = ssl.PrivateCertificate.loadPEM(certPEMData)
    factory = protocol.Factory.forProtocol(Echo)
    reactor.listenSSL(8000, factory, certificate.options())
    return defer.Deferred()

if __name__ == '__main__':
    task.react(main)
