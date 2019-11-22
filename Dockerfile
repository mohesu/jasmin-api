FROM python:2.7-alpine

RUN apk add busybox-extras bash

COPY . .

RUN pip install -r requirements.txt

RUN chmod +x entrypoint.sh

EXPOSE 8000 8080

ENTRYPOINT ["/entrypoint.sh"]

CMD ["python", "/jasmin_api/run_cherrypy.py"]