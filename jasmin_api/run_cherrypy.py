#!/usr/bin/env python
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from jasmin_api.wsgi import application

from django.conf import settings

import cherrypy

if settings.JASMIN_K8S:
    try:
        config.load_incluster_config()
        k8s_api_obj = client.CoreV1Api()
        print "Main: K8S API initialized. settings.JASMIN_K8S: {}".format(settings.JASMIN_K8S)
    except config.ConfigException as e:
        print "Main:ERROR: Cannot initialize K8S environment, terminating:", e
        sys.exit(-1)

cherrypy.tree.graft(application, "/")

cherrypy.tree.mount(None, settings.STATIC_URL, {'/': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': settings.STATIC_ROOT,
        'tools.expires.on': True,
        'tools.expires.secs': 86400
    }
})

server = cherrypy._cpserver.Server()

server.socket_host = "0.0.0.0"
server.socket_port = 8000
server.thread_pool = 10

server.subscribe()

cherrypy.engine.start()
cherrypy.engine.block()
